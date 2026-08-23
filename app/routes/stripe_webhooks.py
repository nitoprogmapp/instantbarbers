import os

import stripe

from fastapi import APIRouter, HTTPException, Request

from app.database import SessionLocal
from app.models.barber import Barber
from app.models.booking import Booking, BookingStatus


router = APIRouter(
    prefix="/stripe",
    tags=["Stripe Webhooks"]
)


def read_value(data, key, default=None):
    if isinstance(data, dict):
        return data.get(key, default)

    return getattr(data, key, default)


def update_barber_account(account):
    stripe_account_id = read_value(account, "id")

    if not stripe_account_id:
        return

    db = SessionLocal()

    try:
        barber = db.query(Barber).filter(
            Barber.stripe_account_id == stripe_account_id
        ).first()

        if not barber:
            return

        charges_enabled = bool(
            read_value(account, "charges_enabled", False)
        )

        payouts_enabled = bool(
            read_value(account, "payouts_enabled", False)
        )

        capabilities = read_value(account, "capabilities")

        card_payments_enabled = (
            read_value(capabilities, "card_payments") == "active"
        )

        transfers_enabled = (
            read_value(capabilities, "transfers") == "active"
        )

        account_enabled = (
            charges_enabled
            and payouts_enabled
            and card_payments_enabled
            and transfers_enabled
        )

        if hasattr(barber, "stripe_charges_enabled"):
            barber.stripe_charges_enabled = charges_enabled

        if hasattr(barber, "stripe_payouts_enabled"):
            barber.stripe_payouts_enabled = payouts_enabled

        if hasattr(barber, "stripe_status"):
            barber.stripe_status = (
                "enabled" if account_enabled else "restricted"
            )

        if not account_enabled:
            barber.active = False

            if hasattr(barber, "last_seen_at"):
                barber.last_seen_at = None

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def update_booking_payment(checkout_session, connected_account_id):
    metadata = read_value(checkout_session, "metadata")
    booking_id = read_value(metadata, "booking_id")

    if not booking_id:
        return

    if read_value(checkout_session, "payment_status") != "paid":
        return

    db = SessionLocal()

    try:
        booking = db.query(Booking).filter(
            Booking.id == int(booking_id)
        ).first()

        if not booking:
            return

        barber = db.query(Barber).filter(
            Barber.id == booking.barber_id
        ).first()

        if not barber:
            return

        if barber.stripe_account_id != connected_account_id:
            return

        if booking.status == BookingStatus.accepted:
            booking.status = BookingStatus.paid
            booking.expires_at = None
            db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


@router.post("/webhook")
async def receive_stripe_webhook(request: Request):
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        raise HTTPException(
            status_code=500,
            detail="STRIPE_WEBHOOK_SECRET no está configurada."
        )

    signature = request.headers.get("stripe-signature")

    if not signature:
        raise HTTPException(
            status_code=400,
            detail="Falta la firma de Stripe."
        )

    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload,
            signature,
            webhook_secret
        )

    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(
            status_code=400,
            detail="La firma del webhook no es válida."
        )

    event_type = read_value(event, "type")
    event_data = read_value(event, "data")
    event_object = read_value(event_data, "object")
    connected_account_id = read_value(event, "account")

    if event_type == "account.updated":
        update_barber_account(event_object)

    elif event_type == "checkout.session.completed":
        update_booking_payment(
            event_object,
            connected_account_id
        )

    return {"received": True}