from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.database import get_db
from app.models.user import User, UserRole
from app.models.barber import Barber
from app.models.booking import Booking, BookingStatus
from app.routes.auth import get_current_user


router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)


BARBER_ONLINE_TIMEOUT_SECONDS = 90
LOCAL_TIMEZONE = ZoneInfo("America/Toronto")


def ensure_user_is_admin(current_user: User):
    role = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else current_user.role
    )

    if role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )


@router.get("/metrics")
def get_admin_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_user_is_admin(current_user)

    registered_barbers = (
        db.query(func.count(User.id))
        .filter(User.role == UserRole.barber)
        .scalar()
        or 0
    )

    activated_barbers = (
        db.query(
            func.count(
                func.distinct(Booking.barber_id)
            )
        )
        .filter(
            Booking.status == BookingStatus.completed,
            Booking.barber_id.isnot(None),
        )
        .scalar()
        or 0
    )

    online_cutoff = (
        datetime.utcnow()
        - timedelta(
            seconds=BARBER_ONLINE_TIMEOUT_SECONDS
        )
    )

    online_barbers = (
        db.query(func.count(Barber.id))
        .filter(
            Barber.active.is_(True),
            Barber.last_seen_at.isnot(None),
            Barber.last_seen_at >= online_cutoff,
        )
        .scalar()
        or 0
    )

    registered_clients = (
        db.query(func.count(User.id))
        .filter(User.role == UserRole.client)
        .scalar()
        or 0
    )

    activated_clients = (
        db.query(
            func.count(
                func.distinct(Booking.client_id)
            )
        )
        .filter(
            Booking.status == BookingStatus.completed,
            Booking.client_id.isnot(None),
        )
        .scalar()
        or 0
    )

    now_local = datetime.now(LOCAL_TIMEZONE)

    start_local = now_local.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    end_local = start_local + timedelta(days=1)

    start_utc = (
        start_local
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )

    end_utc = (
        end_local
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )

    haircuts_today = (
        db.query(func.count(Booking.id))
        .filter(
            Booking.status == BookingStatus.completed,
            Booking.completed_at.isnot(None),
            Booking.completed_at >= start_utc,
            Booking.completed_at < end_utc,
        )
        .scalar()
        or 0
    )

    return {
        "barbers": {
            "registered": registered_barbers,
            "activated": activated_barbers,
            "online": online_barbers,
        },
        "clients": {
            "registered": registered_clients,
            "activated": activated_clients,
        },
        "haircuts": {
            "completed_today": haircuts_today,
        },
    }
