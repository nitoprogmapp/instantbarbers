import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.database import get_db
from app.models.booking import Booking, BookingStatus
from app.models.payment_attempt import PaymentAttempt
from app.models.payment_connection import PaymentConnection
from app.models.square_webhook import SquarePaymentRefund, SquareWebhookEvent
from app.routes.square_payments import decrypt, payment_matches, value_of

router = APIRouter(prefix="/payments/square", tags=["Square Webhooks"])
logger = logging.getLogger(__name__)
MAX_BODY_BYTES = 1024 * 1024
SUPPORTED_EVENTS = {
    "payment.created", "payment.updated", "refund.created", "refund.updated",
    "oauth.authorization.revoked",
}


def square_datetime(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(400, "Invalid Square timestamp.")


def webhook_config():
    # This stage installs Sandbox webhooks only. Production is enabled in block 9.
    if os.getenv("SQUARE_ENVIRONMENT", "").lower() != "sandbox":
        raise HTTPException(503, "Square Sandbox webhook configuration is required.")
    key = os.getenv("SQUARE_WEBHOOK_SIGNATURE_KEY", "")
    url = os.getenv("SQUARE_WEBHOOK_NOTIFICATION_URL", "")
    if not key or not url.startswith("https://"):
        raise HTTPException(503, "Square webhook signature key and notification URL are not configured.")
    return key, url


def valid_signature(raw, signature, key, url):
    expected = base64.b64encode(hmac.new(
        key.encode("utf-8"), url.encode("utf-8") + raw, hashlib.sha256
    ).digest())
    try:
        return hmac.compare_digest(expected, signature.encode("ascii"))
    except (UnicodeEncodeError, AttributeError):
        return False


def event_object(event, name):
    data = event.get("data")
    obj = data.get("object") if isinstance(data, dict) else None
    value = obj.get(name) if isinstance(obj, dict) else None
    if not isinstance(value, dict):
        raise HTTPException(400, "Missing Square event object.")
    return value


def lock_attempt(db, candidate):
    # Match the booking-first lock order used by the payment/cancel/expiry routes.
    booking = db.query(Booking).filter(Booking.id == candidate.booking_id).populate_existing().with_for_update().first()
    attempt = db.query(PaymentAttempt).filter(PaymentAttempt.id == candidate.id).populate_existing().first()
    if not booking or not attempt:
        raise HTTPException(503, "Square payment record is not ready; retry notification.")
    return booking, attempt


def link_refunds(db, attempt):
    # Refund delivery can precede the payment response/webhook. Keep the signed
    # refund durably, then attach it only when its seller, location and amount match.
    rows = db.query(SquarePaymentRefund).filter_by(environment="sandbox",
        merchant_id=attempt.merchant_id, payment_id=attempt.payment_id,
        payment_attempt_id=None).all()
    for refund in rows:
        if (refund.location_id == attempt.location_id and refund.currency == attempt.currency
                and 0 < refund.amount_cents <= attempt.amount_cents):
            refund.payment_attempt_id = attempt.id


def handle_payment(db, event, receipt):
    payment = event_object(event, "payment")
    payment_id = payment.get("id")
    if not isinstance(payment_id, str) or not payment_id:
        raise HTTPException(400, "Missing Square payment ID.")
    candidate = db.query(PaymentAttempt).filter_by(
        environment="sandbox", merchant_id=event["merchant_id"], payment_id=payment_id
    ).first()
    if not candidate:
        reference = payment.get("reference_id", "")
        if not isinstance(reference, str) or not reference.startswith("booking:"):
            return "ignored_unrelated_payment"
        try:
            booking_id = int(reference.split(":", 1)[1])
        except ValueError:
            return "ignored_unrelated_payment"
        candidates = db.query(PaymentAttempt).filter_by(
            environment="sandbox", merchant_id=event["merchant_id"], booking_id=booking_id
        ).all()
        if not candidates:
            return "ignored_unrelated_payment"
        # A reference alone cannot distinguish several attempts for one booking.
        # Let Square redeliver after the payment response/client retry saves its ID.
        if len(candidates) != 1:
            raise HTTPException(503, "Awaiting exact payment ID; retry notification.")
        candidate = candidates[0]
    booking, attempt = lock_attempt(db, candidate)
    if attempt.payment_id and attempt.payment_id != payment_id:
        return "ignored_different_payment"
    expected_fee = None
    if attempt.request_encrypted:
        try:
            expected_fee = json.loads(decrypt(attempt.request_encrypted)).get("app_fee_money")
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(503, "Saved payment terms are unavailable; retry notification.")
    if not payment_matches(payment, attempt, expected_fee):
        if attempt.status != "completed":
            attempt.status = "review"
            attempt.error_code = "PAYMENT_DETAILS_MISMATCH"
        return "review_payment_details"
    receipt.payment_id = payment_id
    receipt.payment_status = payment.get("status")
    fee = payment.get("app_fee_money")
    if isinstance(fee, dict) and fee.get("currency") == attempt.currency and type(fee.get("amount")) is int:
        receipt.app_fee_cents = fee["amount"]
    # A delayed notification must never rewind a completed payment/service.
    if attempt.status == "completed":
        link_refunds(db, attempt)
        return "already_completed"
    status = payment.get("status")
    if status == "COMPLETED":
        attempt.payment_id = payment_id
        attempt.status = "completed"
        attempt.error_code = None
        attempt.request_encrypted = None
        link_refunds(db, attempt)
        if value_of(booking.status) in ("accepted", "paid"):
            booking.status = BookingStatus.paid
            booking.expires_at = None
        elif value_of(booking.status) != "completed":
            attempt.error_code = "BOOKING_STATE_REQUIRES_REVIEW"
        return "payment_completed"
    if attempt.status == "failed":
        return "already_failed"
    if status in ("FAILED", "CANCELED"):
        attempt.payment_id = payment_id
        attempt.status = "failed"
        attempt.error_code = "CARD_PAYMENT_FAILED"
        attempt.request_encrypted = None
        return "payment_failed"
    if status == "APPROVED":
        attempt.payment_id = payment_id
        attempt.status = "approved"
        attempt.error_code = "PAYMENT_PENDING"
        return "payment_approved"
    return "ignored_payment_status"


def handle_refund(db, event, receipt):
    refund = event_object(event, "refund")
    refund_id, payment_id = refund.get("id"), refund.get("payment_id")
    if not isinstance(refund_id, str) or not refund_id or not isinstance(payment_id, str) or not payment_id:
        raise HTTPException(400, "Missing Square refund/payment ID.")
    candidate = db.query(PaymentAttempt).filter_by(
        environment="sandbox", merchant_id=event["merchant_id"], payment_id=payment_id
    ).first()
    if not candidate:
        seller = db.query(PaymentConnection.id).filter_by(
            provider="square", environment="sandbox", merchant_id=event["merchant_id"]
        ).first()
        if not seller:
            return "ignored_unrelated_refund"
        attempt = None
    else:
        _, attempt = lock_attempt(db, candidate)
    money = refund.get("amount_money", {})
    status = refund.get("status")
    location_id = refund.get("location_id")
    if (not isinstance(location_id, str) or not location_id
            or not isinstance(money, dict) or money.get("currency") != "CAD"
            or type(money.get("amount")) is not int
            or not 0 < money["amount"] <= 2147483647
            or (attempt is not None and (location_id != attempt.location_id or money["amount"] > attempt.amount_cents))
            or status not in ("PENDING", "COMPLETED", "FAILED", "REJECTED")):
        return "review_refund_details"
    updated = square_datetime(refund.get("updated_at") or refund.get("created_at"))
    saved = db.query(SquarePaymentRefund).filter_by(environment="sandbox", refund_id=refund_id).first()
    if saved:
        if (saved.payment_id != payment_id or saved.merchant_id != event["merchant_id"]
                or saved.location_id != location_id or saved.amount_cents != money["amount"]
                or saved.currency != money["currency"]):
            return "review_refund_details"
        if attempt is not None:
            saved.payment_attempt_id = attempt.id
        if saved.square_updated_at >= updated or saved.status == "COMPLETED":
            return "ignored_old_refund"
    else:
        saved = SquarePaymentRefund(environment="sandbox", refund_id=refund_id,
            payment_attempt_id=attempt.id if attempt else None, payment_id=payment_id,
            merchant_id=event["merchant_id"], location_id=location_id,
            amount_cents=money["amount"], currency=money["currency"])
        db.add(saved)
    saved.status = status
    saved.square_updated_at = updated
    fee = refund.get("app_fee_money")
    if isinstance(fee, dict) and fee.get("currency") == money["currency"] and type(fee.get("amount")) is int:
        saved.app_fee_cents = fee["amount"]
    receipt.payment_id = payment_id
    # Refunds are financial records; they do not erase a completed haircut or
    # change the original charge to a failed/retryable payment.
    return "refund_" + status.lower()


def handle_revocation(db, event):
    revocation = event_object(event, "revocation")
    revoked_at = square_datetime(revocation.get("revoked_at"))
    rows = db.query(PaymentConnection).filter_by(
        provider="square", environment="sandbox", merchant_id=event["merchant_id"]
    ).populate_existing().with_for_update().all()
    changed = 0
    for connection in rows:
        # Ignore an old revocation delivered after a fresh OAuth connection.
        if connection.connected_at and connection.connected_at > revoked_at:
            continue
        connection.status = "disconnected"
        connection.access_token_encrypted = None
        connection.refresh_token_encrypted = None
        connection.token_expires_at = None
        changed += 1
    return "authorization_revoked" if changed else "ignored_old_or_unrelated_revocation"


def process_event(db, event, digest):
    previous = db.query(SquareWebhookEvent).filter_by(environment="sandbox", event_id=event["event_id"]).first()
    if previous:
        if previous.body_sha256 != digest:
            raise HTTPException(400, "Square event ID was reused with a different body.")
        return {"received": True, "duplicate": True}
    receipt = SquareWebhookEvent(environment="sandbox", event_id=event["event_id"],
        event_type=event["type"], merchant_id=event["merchant_id"], body_sha256=digest)
    db.add(receipt)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        previous = db.query(SquareWebhookEvent).filter_by(environment="sandbox", event_id=event["event_id"]).first()
        if previous and previous.body_sha256 == digest:
            return {"received": True, "duplicate": True}
        raise HTTPException(503, "Square event could not be recorded; retry notification.")
    event_type = event["type"]
    if event_type.startswith("payment.") and event_type in SUPPORTED_EVENTS:
        receipt.outcome = handle_payment(db, event, receipt)
    elif event_type.startswith("refund.") and event_type in SUPPORTED_EVENTS:
        receipt.outcome = handle_refund(db, event, receipt)
    elif event_type == "oauth.authorization.revoked":
        receipt.outcome = handle_revocation(db, event)
    else:
        receipt.outcome = "ignored_event_type"
    receipt.processed_at = datetime.utcnow()
    db.commit()
    return {"received": True}


@router.post("/webhook")
async def square_webhook(request: Request, db: Session = Depends(get_db)):
    key, url = webhook_config()
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BODY_BYTES:
            raise HTTPException(413, "Square event body is too large.")
    raw = bytes(raw)
    if not valid_signature(raw, request.headers.get("x-square-hmacsha256-signature", ""), key, url):
        raise HTTPException(403, "Invalid Square webhook signature.")
    if request.headers.get("square-environment", "sandbox").lower() != "sandbox":
        raise HTTPException(400, "Wrong Square webhook environment.")
    try:
        event = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid Square event JSON.")
    if not isinstance(event, dict) or any(
        not isinstance(event.get(field), str) or not 0 < len(event[field]) <= 255
        for field in ("event_id", "type", "merchant_id")
    ):
        raise HTTPException(400, "Missing or invalid Square event metadata.")
    try:
        return await run_in_threadpool(process_event, db, event, hashlib.sha256(raw).hexdigest())
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError:
        db.rollback()
        # Do not log event bodies, card details, OAuth tokens or database URLs.
        logger.error("Square webhook database processing failed; Square must retry.")
        raise HTTPException(503, "Square webhook could not be saved; retry notification.")
    