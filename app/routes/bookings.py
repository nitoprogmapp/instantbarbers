from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.models.booking import Booking, BookingStatus
from app.models.barber import Barber
from app.models.service import Service
from app.models.user import User
from app.models.client import Client

from app.routes.auth import get_current_user


router = APIRouter(prefix="/bookings", tags=["Bookings"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def role_value(role):
    return role.value if hasattr(role, "value") else role


def status_value(status):
    return status.value if hasattr(status, "value") else status


def mark_booking_expired_safely(booking: Booking, db: Session):
    try:
        if hasattr(BookingStatus, "expired"):
            booking.status = BookingStatus.expired
            db.commit()
            db.refresh(booking)
        else:
            db.rollback()
    except Exception:
        db.rollback()


def expire_old_pending_bookings_for_barber(barber_id: int, db: Session):
    now = datetime.utcnow()

    old_pending_bookings = db.query(Booking).filter(
        Booking.barber_id == barber_id,
        Booking.status == BookingStatus.pending,
        Booking.expires_at != None,
        Booking.expires_at < now
    ).all()

    for booking in old_pending_bookings:
        booking.status = BookingStatus.expired

    if old_pending_bookings:
        db.commit()


# CREATE BOOKING (CLIENTE LOGUEADO)
@router.post("/")
def create_booking(
    barber_id: int,
    service_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if role_value(current_user.role) != "client":
        raise HTTPException(status_code=403, detail="Only clients can create bookings")

    barber = db.query(Barber).filter(Barber.id == barber_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")

    service = db.query(Service).filter(Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    now = datetime.utcnow()

    booking = Booking(
        client_id=current_user.id,
        barber_id=barber_id,
        service_id=service_id,
        status=BookingStatus.pending,
        expires_at=now + timedelta(seconds=30)
    )

    db.add(booking)
    db.commit()
    db.refresh(booking)

    return booking


# BARBER BOOKINGS (BARBERO LOGUEADO)
@router.get("/barber/me")
def get_my_bookings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if role_value(current_user.role) != "barber":
        raise HTTPException(status_code=403, detail="Only barbers can view bookings")

    barber = db.query(Barber).filter(Barber.user_id == current_user.id).first()

    if not barber:
        raise HTTPException(status_code=404, detail="Barber profile not found")

    expire_old_pending_bookings_for_barber(barber.id, db)

    bookings = db.query(Booking).filter(
        Booking.barber_id == barber.id,
        Booking.status == BookingStatus.pending
    ).all()

    results = []

    for booking in bookings:
        client = db.query(Client).filter(Client.user_id == booking.client_id).first()

        results.append({
            "id": booking.id,
            "client_id": booking.client_id,
            "barber_id": booking.barber_id,
            "service_id": booking.service_id,
            "status": status_value(booking.status),
            "created_at": booking.created_at,
            "accepted_at": booking.accepted_at,
            "expires_at": booking.expires_at,
            "payment_intent_id": booking.payment_intent_id,
            "client": {
                "name": client.name if client else None,
                "phone": client.phone if client else None,
                "address": client.address if client else None
            }
        })

    return results


# GET BOOKING
@router.get("/{booking_id}")
def get_booking(booking_id: int, db: Session = Depends(get_db)):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if status_value(booking.status) == "pending" and booking.expires_at:
        now = datetime.utcnow()

        if now > booking.expires_at:
            mark_booking_expired_safely(booking, db)

    return booking


# ACCEPT BOOKING (BARBERO LOGUEADO)
@router.put("/{booking_id}/accept")
def accept_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if role_value(current_user.role) != "barber":
        raise HTTPException(status_code=403, detail="Only barbers can accept bookings")

    barber = db.query(Barber).filter(Barber.user_id == current_user.id).first()

    if not barber:
        raise HTTPException(status_code=404, detail="Barber profile not found")

    booking = db.query(Booking).filter(Booking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.barber_id != barber.id:
        raise HTTPException(status_code=403, detail="Not your booking")

    if status_value(booking.status) != "pending":
        raise HTTPException(status_code=400, detail="Invalid state")

    now = datetime.utcnow()

    if booking.expires_at and now > booking.expires_at:
        mark_booking_expired_safely(booking, db)
        raise HTTPException(status_code=400, detail="Booking expired because barber did not accept in time")

    booking.status = BookingStatus.accepted
    booking.accepted_at = now
    booking.expires_at = now + timedelta(seconds=30)

    db.commit()
    db.refresh(booking)

    return booking


# REFUSE BOOKING (BARBERO LOGUEADO)
@router.put("/{booking_id}/refuse")
def refuse_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if role_value(current_user.role) != "barber":
        raise HTTPException(status_code=403, detail="Only barbers can refuse bookings")

    barber = db.query(Barber).filter(Barber.user_id == current_user.id).first()

    if not barber:
        raise HTTPException(status_code=404, detail="Barber profile not found")

    booking = db.query(Booking).filter(Booking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.barber_id != barber.id:
        raise HTTPException(status_code=403, detail="Not your booking")

    if status_value(booking.status) != "pending":
        raise HTTPException(status_code=400, detail="Only pending bookings can be refused")

    booking.status = BookingStatus.cancelled

    db.commit()
    db.refresh(booking)

    return booking


# PAY BOOKING (CLIENTE LOGUEADO)
@router.put("/{booking_id}/paid")
def pay_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if role_value(current_user.role) != "client":
        raise HTTPException(status_code=403, detail="Only clients can pay")

    booking = db.query(Booking).filter(Booking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.client_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your booking")

    if status_value(booking.status) != "accepted":
        raise HTTPException(status_code=400, detail="Must be accepted first")

    if booking.expires_at:
        now = datetime.utcnow()

        if now > booking.expires_at:
            mark_booking_expired_safely(booking, db)
            raise HTTPException(status_code=400, detail="Expired")

    booking.status = BookingStatus.paid

    db.commit()
    db.refresh(booking)

    return booking


# COMPLETE BOOKING (CLIENTE LOGUEADO)
@router.put("/{booking_id}/complete")
def complete_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if role_value(current_user.role) != "client":
        raise HTTPException(status_code=403, detail="Only clients can complete")

    booking = db.query(Booking).filter(Booking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.client_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your booking")

    if status_value(booking.status) != "paid":
        raise HTTPException(status_code=400, detail="Must be paid first")

    booking.status = BookingStatus.completed

    db.commit()
    db.refresh(booking)

    return booking