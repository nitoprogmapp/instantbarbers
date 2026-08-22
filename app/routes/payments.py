import asyncio
import os

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

import stripe

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.database import SessionLocal
from app.models.booking import Booking, BookingStatus
from app.models.barber import Barber
from app.routes.auth import get_current_user


router = APIRouter(prefix="/payments")

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "https://instantbarbers.com"
).rstrip("/")

BACKEND_URL = os.getenv(
    "BACKEND_URL",
    "https://instantbarbers.onrender.com"
).rstrip("/")

PAYMENT_TIMEOUT_SECONDS = 90

payment_expiration_tasks = set()


@router.post("/create-payment-intent")
def create_payment_test():
    return {"message": "payment endpoint working"}


async def expire_unpaid_checkout(
    booking_id: int,
    checkout_session_id: str,
    stripe_account_id: str
):
    await asyncio.sleep(PAYMENT_TIMEOUT_SECONDS)

    db = SessionLocal()

    try:
        booking = db.query(Booking).filter(
            Booking.id == booking_id
        ).first()

        if not booking or booking.status in (
    BookingStatus.paid,
    BookingStatus.completed,
    BookingStatus.cancelled,
    BookingStatus.expired,
):
    return

        session = await run_in_threadpool(
            stripe.checkout.Session.retrieve,
            checkout_session_id,
            stripe_account=stripe_account_id
        )

        if session.payment_status == "paid":
            booking.status = BookingStatus.paid
            booking.expires_at = None
            db.commit()
            return

        if session.status == "open":
            await run_in_threadpool(
                stripe.checkout.Session.expire,
                checkout_session_id,
                stripe_account=stripe_account_id
            )

        if booking.status == BookingStatus.accepted:
            booking.status = BookingStatus.expired
            db.commit()

    except Exception as error:
        db.rollback()

        print(
            f"Error while expiring payment for booking "
            f"{booking_id}: {error}"
        )

    finally:
        db.close()


@router.post("/pay")
async def pay(
    booking_id: int,
    current_user=Depends(get_current_user)
):
    db = SessionLocal()

    try:
        booking = db.query(Booking).filter(
            Booking.id == booking_id
        ).first()

        if not booking:
            raise HTTPException(
                status_code=404,
                detail="Booking not found"
            )

        if booking.client_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="This booking belongs to another customer"
            )

        if booking.status != BookingStatus.accepted:
            raise HTTPException(
                status_code=400,
                detail="Booking not payable"
            )

        if (
            booking.expires_at
            and datetime.utcnow() > booking.expires_at
        ):
            booking.status = BookingStatus.expired
            db.commit()

            raise HTTPException(
                status_code=400,
                detail="Booking expired"
            )

        barber = db.query(Barber).filter(
            Barber.id == booking.barber_id
        ).first()

        if not barber:
            raise HTTPException(
                status_code=400,
                detail="Barber not found"
            )

        stripe_account_id = getattr(
            barber,
            "stripe_account_id",
            None
        )

        if not stripe_account_id:
            raise HTTPException(
                status_code=400,
                detail="Barber has no Stripe account"
            )

        if not barber.price:
            raise HTTPException(
                status_code=400,
                detail="Barber has no price"
            )

        amount_cents = int(
            (
                Decimal(str(barber.price))
                * Decimal("100")
            ).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP
            )
        )

        app_fee = int(
            (
                Decimal(amount_cents)
                * Decimal("0.03")
            ).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP
            )
        )

        session = await run_in_threadpool(
            stripe.checkout.Session.create,
            mode="payment",
            payment_method_types=["card"],
            customer_email=current_user.email,
            line_items=[
                {
                    "price_data": {
                        "currency": "cad",
                        "product_data": {
                            "name": "InstantBarbers haircut"
                        },
                        "unit_amount": amount_cents
                    },
                    "quantity": 1
                }
            ],
            payment_intent_data={
                "application_fee_amount": app_fee,
                "metadata": {
                    "booking_id": str(booking.id)
                }
            },
            metadata={
                "booking_id": str(booking.id),
                "customer_user_id": str(current_user.id)
            },
            success_url=(
                f"{BACKEND_URL}/payments/return"
                f"?booking_id={booking.id}"
                f"&session_id={{CHECKOUT_SESSION_ID}}"
            ),
            cancel_url=(
                f"{FRONTEND_URL}/customer/booking-status"
                f"?payment=cancelled"
                f"&booking_id={booking.id}"
            ),
            stripe_account=stripe_account_id
        )

        booking.expires_at = (
            datetime.utcnow()
            + timedelta(seconds=PAYMENT_TIMEOUT_SECONDS)
        )

        db.commit()

        task = asyncio.create_task(
            expire_unpaid_checkout(
                booking.id,
                session.id,
                stripe_account_id
            )
        )

        payment_expiration_tasks.add(task)

        task.add_done_callback(
            payment_expiration_tasks.discard
        )

        return {
            "checkout_url": session.url,
            "session_id": session.id,
            "payment_timeout_seconds": PAYMENT_TIMEOUT_SECONDS
        }

    except HTTPException:
        raise

    except stripe.StripeError as error:
        db.rollback()

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception as error:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )

    finally:
        db.close()


@router.get("/return")
async def return_from_stripe(
    booking_id: int,
    session_id: str
):
    db = SessionLocal()

    try:
        booking = db.query(Booking).filter(
            Booking.id == booking_id
        ).first()

        if not booking:
            raise HTTPException(
                status_code=404,
                detail="Booking not found"
            )

        barber = db.query(Barber).filter(
            Barber.id == booking.barber_id
        ).first()

        if not barber or not barber.stripe_account_id:
            raise HTTPException(
                status_code=400,
                detail="Barber has no Stripe account"
            )

        session = await run_in_threadpool(
            stripe.checkout.Session.retrieve,
            session_id,
            stripe_account=barber.stripe_account_id
        )

        metadata = session.metadata.to_dict() if session.metadata else {}

        if metadata.get("booking_id") != str(booking.id):
            raise HTTPException(
                status_code=400,
                detail="Payment does not belong to this booking"
            )

        if metadata.get("customer_user_id") != str(
            booking.client_id
        ):
            raise HTTPException(
                status_code=403,
                detail="Payment does not belong to this customer"
            )

        if session.payment_status != "paid":
            raise HTTPException(
                status_code=400,
                detail="Payment has not been completed"
            )

        booking.status = BookingStatus.paid
        booking.expires_at = None

        db.commit()

        return RedirectResponse(
            url=(
                f"{FRONTEND_URL}/customer/booking-status"
                f"?booking_id={booking.id}"
            ),
            status_code=303
        )

    except HTTPException:
        raise

    except stripe.StripeError as error:
        db.rollback()

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception as error:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )

    finally:
        db.close()


@router.get("/confirm")
async def confirm_payment(
    booking_id: int,
    session_id: str,
    current_user=Depends(get_current_user)
):
    db = SessionLocal()

    try:
        booking = db.query(Booking).filter(
            Booking.id == booking_id
        ).first()

        if not booking:
            raise HTTPException(
                status_code=404,
                detail="Booking not found"
            )

        barber = db.query(Barber).filter(
            Barber.id == booking.barber_id
        ).first()

        if not barber or not barber.stripe_account_id:
            raise HTTPException(
                status_code=400,
                detail="Barber has no Stripe account"
            )

        session = await run_in_threadpool(
            stripe.checkout.Session.retrieve,
            session_id,
            stripe_account=barber.stripe_account_id
        )

        metadata = session.metadata or {}

        if metadata.get("booking_id") != str(booking.id):
            raise HTTPException(
                status_code=400,
                detail="Payment does not belong to this booking"
            )

        if metadata.get("customer_user_id") != str(
            current_user.id
        ):
            raise HTTPException(
                status_code=403,
                detail="Payment does not belong to this customer"
            )

        if session.payment_status != "paid":
            raise HTTPException(
                status_code=400,
                detail="Payment has not been completed"
            )

        booking.status = BookingStatus.paid
        booking.expires_at = None

        db.commit()

        return {
            "booking_id": booking.id,
            "status": "paid"
        }

    except HTTPException:
        raise

    except stripe.StripeError as error:
        db.rollback()

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception as error:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )

    finally:
        db.close()