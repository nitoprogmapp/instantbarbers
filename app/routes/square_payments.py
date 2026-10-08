import json
import os
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import UUID
from typing import Literal

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.barber import Barber
from app.models.booking import Booking, BookingStatus
from app.models.payment_connection import PaymentConnection
from app.models.payment_attempt import PaymentAttempt, UNRESOLVED_PAYMENT_STATUSES
from app.routes.auth import get_current_user
from app.routes.square_token_refresh import renew_if_due

router = APIRouter(prefix="/payments/square", tags=["Square Payments"])
API_VERSION = "2026-08-19"


class CardPaymentRequest(BaseModel):
    booking_id: int = Field(gt=0)
    source_id: str = Field(min_length=1, max_length=1024)
    idempotency_key: str = Field(min_length=36, max_length=36)
    expected_amount_cents: int = Field(gt=0)
    environment: Literal["sandbox", "production"] | None = None


def current_environment():
    environment = os.getenv("SQUARE_ENVIRONMENT", "").lower()
    if environment not in ("sandbox", "production"):
        raise HTTPException(503, "Square payment environment is missing or invalid.")
    return environment


def square_config():
    environment = current_environment()
    app_id = os.getenv("SQUARE_APPLICATION_ID", "")
    if not app_id or app_id.startswith("sandbox-") != (environment == "sandbox"):
        raise HTTPException(503, "SQUARE_APPLICATION_ID does not match the payment environment.")
    return app_id


def assert_attempt_environment(attempt):
    if attempt and attempt.environment != current_environment():
        raise HTTPException(409, "This booking contains a payment from another Square environment. Start a new booking.")


def cipher():
    try:
        return Fernet(os.environ["PAYMENT_TOKEN_ENCRYPTION_KEY"].encode())
    except (KeyError, ValueError):
        raise HTTPException(503, "Payment encryption configuration is missing or invalid.")


def decrypt(value):
    try:
        return cipher().decrypt((value or "").encode()).decode()
    except InvalidToken:
        raise HTTPException(503, "The saved payment credentials cannot be decrypted.")


def money_cents(price):
    try:
        value = Decimal(str(price))
        if not value.is_finite() or value <= 0:
            raise ValueError()
        cents = int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if cents <= 0 or cents > 2147483647:
            raise ValueError()
        return cents
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(409, "The barber price is invalid.")


def application_fee_cents(amount_cents):
    # 3% of the gross haircut price, rounded HALF_UP to the nearest CAD cent.
    # Integer arithmetic avoids floating-point errors. Square processing fees
    # are separate and do not reduce the base used to calculate our 3%.
    return (amount_cents * 3 + 50) // 100


def value_of(value):
    return getattr(value, "value", value)


def client_booking(db, booking_id, user):
    if value_of(user.role) != "client":
        raise HTTPException(403, "Only clients can pay for a booking.")
    booking = db.query(Booking).filter(Booking.id == booking_id).populate_existing().with_for_update().first()
    if not booking:
        raise HTTPException(404, "Booking not found.")
    if booking.client_id != user.id:
        raise HTTPException(403, "Not your booking.")
    return booking


def latest_attempt(db, booking_id):
    attempt = db.query(PaymentAttempt).filter(
        PaymentAttempt.booking_id == booking_id
    ).order_by(PaymentAttempt.id.desc()).first()
    assert_attempt_environment(attempt)
    return attempt


def connection(db, booking, attempt=None):
    saved = db.query(PaymentConnection).filter(
        PaymentConnection.barber_id == booking.barber_id,
        PaymentConnection.provider == "square",
        PaymentConnection.environment == current_environment(),
    ).populate_existing().first()
    if saved and saved.status == "connected":
        renew_if_due(db, saved)
    if not saved or saved.status != "connected" or not saved.access_token_encrypted or not saved.location_id:
        raise HTTPException(409, "The barber is not connected to Square in the current payment environment.")
    if not saved.token_expires_at or saved.token_expires_at <= datetime.utcnow():
        raise HTTPException(503, "Square authorization renewal is temporarily unavailable. Try again shortly.")
    if attempt and (saved.merchant_id != attempt.merchant_id or saved.location_id != attempt.location_id):
        raise HTTPException(409, "The seller connection changed. The previous payment must be reconciled first.")
    return saved, decrypt(saved.access_token_encrypted)


def square_request(token, method, path, payload=None):
    square_config()
    base_url = "https://connect.squareupsandbox.com" if current_environment() == "sandbox" else "https://connect.squareup.com"
    with httpx.Client(timeout=httpx.Timeout(25.0, connect=10.0)) as client:
        return client.request(method, base_url + path, headers={
            "Authorization": "Bearer " + token,
            "Square-Version": API_VERSION,
            "Content-Type": "application/json",
        }, json=payload)


def validate_location(saved, token):
    try:
        response = square_request(token, "GET", "/v2/locations/" + saved.location_id)
        location = response.json().get("location", {})
    except (httpx.HTTPError, ValueError, AttributeError):
        raise HTTPException(502, "Square location verification is temporarily unavailable.")
    if response.status_code != 200 or location.get("id") != saved.location_id or location.get("merchant_id") != saved.merchant_id:
        raise HTTPException(409, "Square could not verify the barber's location.")
    if location.get("status") != "ACTIVE" or "CREDIT_CARD_PROCESSING" not in location.get("capabilities", []):
        raise HTTPException(409, "The barber's Square location cannot process card payments.")
    if location.get("currency") != "CAD" or location.get("country") != "CA":
        raise HTTPException(409, "This checkout requires a Canadian Square location in CAD.")


def assert_payable(booking):
    if value_of(booking.status) != "accepted":
        raise HTTPException(409, "The booking must be accepted before payment.")
    if not booking.expires_at or booking.expires_at <= datetime.utcnow():
        raise HTTPException(409, "The payment window has expired.")


def result(attempt):
    return {
        "booking_id": attempt.booking_id,
        "status": attempt.status,
        "payment_id": attempt.payment_id,
        "amount_cents": attempt.amount_cents,
        "currency": attempt.currency,
        "error_code": attempt.error_code,
        "can_retry": attempt.status in UNRESOLVED_PAYMENT_STATUSES,
    }


def payment_matches(payment, attempt, expected_fee=None):
    # Old attempts created before application fees retain their original terms.
    # For new attempts, verify Square returned the fee we actually submitted.
    if expected_fee is not None and payment.get("app_fee_money") != expected_fee:
        return False
    return (
        payment.get("id")
        and payment.get("source_type") == "CARD"
        and payment.get("location_id") == attempt.location_id
        and payment.get("reference_id") == "booking:" + str(attempt.booking_id)
        and payment.get("amount_money", {}).get("amount") == attempt.amount_cents
        and payment.get("amount_money", {}).get("currency") == attempt.currency
    )


def process_attempt(db, booking, attempt):
    assert_attempt_environment(attempt)
    # The booking row stays locked while Square is contacted. Expiration and
    # cancellation acquire the same lock and never release an unresolved booking.
    _, token = connection(db, booking, attempt)
    try:
        # Recover the original fee and request, never recalculate an existing
        # attempt after a price change or a deployment.
        payload = json.loads(decrypt(attempt.request_encrypted)) if attempt.request_encrypted else {}
        expected_fee = payload.get("app_fee_money")
        if attempt.payment_id:
            response = square_request(token, "GET", "/v2/payments/" + attempt.payment_id)
        else:
            # Stop automatic replays of very old unresolved requests. They must
            # be reconciled; generating a fresh key could create a second charge.
            if attempt.created_at < datetime.utcnow() - timedelta(hours=24):
                attempt.status = "review"
                attempt.error_code = "RECONCILIATION_REQUIRED"
                db.commit()
                return result(attempt)
            response = square_request(token, "POST", "/v2/payments", payload)
        data = response.json()
        payment = data.get("payment")
        if isinstance(payment, dict) and payment_matches(payment, attempt, expected_fee):
            attempt.payment_id = payment["id"]
            payment_status = payment.get("status")
            if payment_status == "COMPLETED":
                attempt.status = "completed"
                attempt.error_code = None
                attempt.request_encrypted = None
                booking.status = BookingStatus.paid
                booking.expires_at = None
            elif payment_status in ("FAILED", "CANCELED"):
                attempt.status = "failed"
                attempt.error_code = "CARD_PAYMENT_FAILED"
                attempt.request_encrypted = None
            else:
                attempt.status = "approved" if payment_status == "APPROVED" else "unknown"
                attempt.error_code = "PAYMENT_PENDING"
        elif payment:
            attempt.status = "review"
            attempt.error_code = "PAYMENT_DETAILS_MISMATCH"
        else:
            # Only explicit card rejection can allow a fresh payment attempt.
            errors = data.get("errors") or []
            codes = [item.get("code", "") for item in errors if isinstance(item, dict)]
            declines = {"CARD_DECLINED", "GENERIC_DECLINE", "CVV_FAILURE", "ADDRESS_VERIFICATION_FAILURE", "INSUFFICIENT_FUNDS", "CARD_EXPIRED", "EXPIRATION_FAILURE", "INVALID_CARD", "INVALID_EXPIRATION", "VERIFY_CVV_FAILURE", "VERIFY_AVS_FAILURE", "CARD_TOKEN_USED", "CARD_TOKEN_EXPIRED"}
            if response.status_code in (400, 402, 422) and codes and all(code in declines for code in codes):
                attempt.status = "failed"
                attempt.error_code = codes[0]
                attempt.request_encrypted = None
            else:
                attempt.status = "unknown"
                attempt.error_code = "SQUARE_RESPONSE_UNCONFIRMED"
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        attempt.status = "unknown"
        attempt.error_code = "SQUARE_RESPONSE_UNCONFIRMED"
    db.commit()
    return result(attempt)


@router.get("/checkout")
def checkout(booking_id: int, response: Response, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    app_id = square_config()
    booking = client_booking(db, booking_id, current_user)
    attempt = latest_attempt(db, booking.id)
    if attempt and attempt.status in UNRESOLVED_PAYMENT_STATUSES + ("completed",):
        return {"attempt": result(attempt), "booking_id": booking.id}
    assert_payable(booking)
    saved, token = connection(db, booking)
    validate_location(saved, token)
    barber = db.query(Barber).filter(Barber.id == booking.barber_id).first()
    if not barber:
        raise HTTPException(404, "Barber not found.")
    return {"booking_id": booking.id, "environment": current_environment(), "application_id": app_id,
            "location_id": saved.location_id, "amount_cents": money_cents(barber.price), "currency": "CAD",
            "buyer_email": getattr(current_user, "email", ""), "expires_at": booking.expires_at}


@router.post("/pay")
def pay(body: CardPaymentRequest, response: Response, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    square_config()
    environment = current_environment()
    # Old Sandbox clients remain compatible. Production requires the new client
    # to explicitly identify its SDK environment before any processor request.
    if body.environment != environment and (body.environment is not None or environment == "production"):
        raise HTTPException(409, "The payment environment changed. Reload the page before paying.")
    try:
        if str(UUID(body.idempotency_key)) != body.idempotency_key:
            raise ValueError()
    except ValueError:
        raise HTTPException(422, "A canonical UUID idempotency key is required.")
    booking = client_booking(db, body.booking_id, current_user)
    attempt = latest_attempt(db, booking.id)
    if attempt and attempt.status == "completed":
        return result(attempt)
    old = db.query(PaymentAttempt).filter(PaymentAttempt.idempotency_key == body.idempotency_key).first()
    if old:
        assert_attempt_environment(old)
        if old.booking_id != booking.id or old.client_id != current_user.id:
            raise HTTPException(409, "This payment key belongs to another request.")
        if old.status == "failed":
            return result(old)
    if not attempt or attempt.status not in UNRESOLVED_PAYMENT_STATUSES:
        assert_payable(booking)
        if booking.payment_intent_id:
            raise HTTPException(409, "An earlier payment exists. Verify it before using Square.")
        saved, token = connection(db, booking)
        validate_location(saved, token)
        # A location lookup can outlast the remaining payment window.
        assert_payable(booking)
        barber = db.query(Barber).filter(Barber.id == booking.barber_id).first()
        if not barber:
            raise HTTPException(404, "Barber not found.")
        amount = money_cents(barber.price)
        if amount != body.expected_amount_cents:
            raise HTTPException(409, "The price changed. Reload the payment form.")
        if body.source_id.upper() in ("CASH", "EXTERNAL"):
            raise HTTPException(422, "A card token from Square Web Payments is required.")
        payload = {"source_id": body.source_id, "idempotency_key": body.idempotency_key,
                   "amount_money": {"amount": amount, "currency": "CAD"}, "autocomplete": True,
                   "location_id": saved.location_id, "reference_id": "booking:" + str(booking.id)}
        fee = application_fee_cents(amount)
        if fee > 0:
            payload["app_fee_money"] = {"amount": fee, "currency": "CAD"}
        attempt = PaymentAttempt(booking_id=booking.id, client_id=current_user.id, barber_id=booking.barber_id,
            environment=environment, merchant_id=saved.merchant_id, location_id=saved.location_id,
            amount_cents=amount, currency="CAD", idempotency_key=body.idempotency_key,
            request_encrypted=cipher().encrypt(json.dumps(payload, sort_keys=True).encode()).decode(), status="processing")
        db.add(attempt)
        db.commit()
        # Persist first, then reacquire the row lock before calling Square.
        booking = client_booking(db, booking.id, current_user)
        attempt = latest_attempt(db, booking.id)
        if attempt.status == "completed":
            return result(attempt)
        if attempt.status == "failed":
            return result(attempt)
    return process_attempt(db, booking, attempt)


@router.post("/retry/{booking_id}")
def retry(booking_id: int, response: Response, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    square_config()
    booking = client_booking(db, booking_id, current_user)
    attempt = latest_attempt(db, booking.id)
    if not attempt:
        raise HTTPException(404, "No Square payment attempt exists.")
    if attempt.status in ("completed", "failed", "review"):
        return result(attempt)
    return process_attempt(db, booking, attempt)