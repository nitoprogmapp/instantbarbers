from fastapi import APIRouter, HTTPException
from app.services.stripe_service import create_payment_intent
from app.database import SessionLocal
from app.models.booking import Booking, BookingStatus
from app.models.barber import Barber
from datetime import datetime

router = APIRouter(prefix="/payments")


@router.post("/create-payment-intent")
def create_payment_test():
    return {"message": "payment endpoint working"}


@router.post("/pay")
def pay(booking_id: int):
    db = SessionLocal()

    try:
        booking = db.query(Booking).filter(Booking.id == booking_id).first()

        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        # 🔥 AUTO-EXPIRE
        if booking.status == BookingStatus.accepted and booking.expires_at:
            if datetime.utcnow() > booking.expires_at:
                booking.status = "expired"
                db.commit()
                raise HTTPException(status_code=400, detail="Booking expired")

        # ❌ bloquear estados finales
        if booking.status in [
            BookingStatus.cancelled,
            BookingStatus.completed,
            "expired"
        ]:
            raise HTTPException(status_code=400, detail="Booking not payable")

        # 🔧 BUSCAR BARBER
        barber = db.query(Barber).filter(Barber.id == booking.barber_id).first()

        if not barber:
            raise HTTPException(status_code=400, detail="Barber not found")

        # 🔧 VALIDAR STRIPE ACCOUNT
        stripe_account = getattr(barber, "stripe_account_id", None)
        if not stripe_account:
            raise HTTPException(status_code=400, detail="Barber has no Stripe account")

        # 🔧 PRECIO
        if not barber.price:
            raise HTTPException(status_code=400, detail="Barber has no price")

        # 💰 CALCULAR 3%
        app_fee = int(barber.price * 0.03)

        # 💳 CREAR PAYMENT INTENT
        intent = create_payment_intent(
            barber.price,
            "cad",
            stripe_account,
            app_fee
        )

        return {"client_secret": intent.client_secret}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    