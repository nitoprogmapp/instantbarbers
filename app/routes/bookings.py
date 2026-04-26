from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.models.booking import Booking, BookingStatus
from app.models.barber import Barber
from app.models.service import Service
from app.models.user import User, UserRole

from app.routes.auth import get_current_user


router = APIRouter(prefix="/bookings", tags=["Bookings"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# CREATE BOOKING (CLIENTE LOGUEADO)
@router.post("/")
def create_booking(
    barber_id: int,
    service_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.client:
        raise HTTPException(status_code=403, detail="Only clients can create bookings")

    barber = db.query(Barber).filter(Barber.id == barber_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")

    service = db.query(Service).filter(Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    booking = Booking(
        client_id=current_user.id,
        barber_id=barber_id,
        service_id=service_id,
        status=BookingStatus.pending
    )

    db.add(booking)
    db.commit()
    db.refresh(booking)

    return booking


# GET BOOKING
@router.get("/{booking_id}")
def get_booking(booking_id: int, db: Session = Depends(get_db)):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    return booking


# BARBER BOOKINGS (BARBER LOGUEADO)
@router.get("/barber/me")
def get_my_bookings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.barber:
        raise HTTPException(status_code=403, detail="Only barbers can view bookings")

    barber = db.query(Barber).filter(Barber.user_id == current_user.id).first()

    if not barber:
        raise HTTPException(status_code=404, detail="Barber profile not found")

    return db.query(Booking).filter(
        Booking.barber_id == barber.id,
        Booking.status == BookingStatus.pending
    ).all()


# ACCEPT BOOKING (BARBER LOGUEADO)
@router.put("/{booking_id}/accept")
def accept_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.barber:
        raise HTTPException(status_code=403, detail="Only barbers can accept bookings")

    barber = db.query(Barber).filter(Barber.user_id == current_user.id).first()

    if not barber:
        raise HTTPException(status_code=404, detail="Barber profile not found")

    booking = db.query(Booking).filter(Booking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.barber_id != barber.id:
        raise HTTPException(status_code=403, detail="Not your booking")

    if booking.status != BookingStatus.pending:
        raise HTTPException(status_code=400, detail="Invalid state")

    booking.status = BookingStatus.accepted
    booking.accepted_at = datetime.utcnow()
    booking.expires_at = datetime.utcnow() + timedelta(seconds=30)

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
    if current_user.role != UserRole.client:
        raise HTTPException(status_code=403, detail="Only clients can pay")

    booking = db.query(Booking).filter(Booking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.client_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your booking")

    if booking.status != BookingStatus.accepted:
        raise HTTPException(status_code=400, detail="Must be accepted first")

    if booking.expires_at and datetime.utcnow() > booking.expires_at:
        booking.status = BookingStatus.expired
        db.commit()
        db.refresh(booking)
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
    if current_user.role != UserRole.client:
        raise HTTPException(status_code=403, detail="Only clients can complete")

    booking = db.query(Booking).filter(Booking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.client_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your booking")

    if booking.status != BookingStatus.paid:
        raise HTTPException(status_code=400, detail="Must be paid first")

    booking.status = BookingStatus.completed

    db.commit()
    db.refresh(booking)

    return booking