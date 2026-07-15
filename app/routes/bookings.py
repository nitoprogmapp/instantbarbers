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


ACTIVE_BOOKING_STATUSES = [
    BookingStatus.pending,
    BookingStatus.accepted,
    BookingStatus.paid,
]

TIME_LIMITED_BOOKING_STATUSES = [
    BookingStatus.pending,
    BookingStatus.accepted,
]


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


def expire_old_time_limited_bookings_for_barber(barber_id: int, db: Session):
    now = datetime.utcnow()

    old_bookings = db.query(Booking).filter(
        Booking.barber_id == barber_id,
        Booking.status.in_(TIME_LIMITED_BOOKING_STATUSES),
        Booking.expires_at != None,
        Booking.expires_at < now
    ).all()

    for booking in old_bookings:
        booking.status = BookingStatus.expired

    if old_bookings:
        db.commit()


def expire_old_time_limited_bookings_for_client(client_user_id: int, db: Session):
    now = datetime.utcnow()

    old_bookings = db.query(Booking).filter(
        Booking.client_id == client_user_id,
        Booking.status.in_(TIME_LIMITED_BOOKING_STATUSES),
        Booking.expires_at != None,
        Booking.expires_at < now
    ).all()

    for booking in old_bookings:
        booking.status = BookingStatus.expired

    if old_bookings:
        db.commit()


def expire_old_time_limited_booking(booking: Booking, db: Session):
    if not booking:
        return

    if status_value(booking.status) not in ["pending", "accepted"]:
        return

    if not booking.expires_at:
        return

    now = datetime.utcnow()

    if now > booking.expires_at:
        mark_booking_expired_safely(booking, db)


def get_active_booking_for_barber(barber_id: int, db: Session):
    expire_old_time_limited_bookings_for_barber(barber_id, db)

    return db.query(Booking).filter(
        Booking.barber_id == barber_id,
        Booking.status.in_(ACTIVE_BOOKING_STATUSES)
    ).order_by(Booking.created_at.asc()).first()


def get_active_booking_for_client(client_user_id: int, db: Session):
    expire_old_time_limited_bookings_for_client(client_user_id, db)

    return db.query(Booking).filter(
        Booking.client_id == client_user_id,
        Booking.status.in_(ACTIVE_BOOKING_STATUSES)
    ).order_by(Booking.created_at.desc()).first()


def booking_to_barber_response(booking: Booking, db: Session):
    client = db.query(Client).filter(Client.user_id == booking.client_id).first()

    return {
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
    }


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

    if barber.active is not True:
        raise HTTPException(
            status_code=409,
            detail="This barber is not available right now. Please choose another barber."
        )

    service = db.query(Service).filter(Service.id == service_id).first()

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    active_booking = get_active_booking_for_barber(barber_id, db)

    if active_booking:
        raise HTTPException(
            status_code=409,
            detail="This barber is no longer available. Please choose another barber."
        )

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

    active_booking = get_active_booking_for_barber(barber.id, db)

    if not active_booking:
        return []

    return [booking_to_barber_response(active_booking, db)]


# CLIENT ACTIVE BOOKING (CLIENTE LOGUEADO)
# IMPORTANTE: Este endpoint debe estar antes de /{booking_id}
@router.get("/client/me/active")
def get_my_active_client_booking(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if role_value(current_user.role) != "client":
        raise HTTPException(status_code=403, detail="Only clients can view their active booking")

    active_booking = get_active_booking_for_client(current_user.id, db)

    if not active_booking:
        raise HTTPException(status_code=404, detail="No active booking found")

    return active_booking


# GET BOOKING
@router.get("/{booking_id}")
def get_booking(booking_id: int, db: Session = Depends(get_db)):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    expire_old_time_limited_booking(booking, db)

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

    expire_old_time_limited_bookings_for_barber(barber.id, db)

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

    other_active_booking = db.query(Booking).filter(
        Booking.barber_id == barber.id,
        Booking.id != booking.id,
        Booking.status.in_(ACTIVE_BOOKING_STATUSES)
    ).first()

    if other_active_booking:
        raise HTTPException(
            status_code=409,
            detail="You already have an active booking."
        )

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


# CANCEL BOOKING BEFORE PAYMENT (CLIENTE LOGUEADO)
@router.put("/{booking_id}/cancel")
def cancel_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if role_value(current_user.role) != "client":
        raise HTTPException(
            status_code=403,
            detail="Only clients can cancel bookings"
        )

    booking = db.query(Booking).filter(Booking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.client_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your booking")

    if status_value(booking.status) != "accepted":
        raise HTTPException(
            status_code=400,
            detail="Only accepted bookings can be cancelled before payment"
        )

    if booking.expires_at:
        now = datetime.utcnow()

        if now > booking.expires_at:
            mark_booking_expired_safely(booking, db)
            raise HTTPException(status_code=400, detail="Booking expired")

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