from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.barber import Barber
from app.models.user import User
from app.routes.auth import get_current_user
from app.schemas.barber import BarberProfileRead, BarberProfileUpdate


router = APIRouter(
    prefix="/barbers",
    tags=["Barbers"]
)


def ensure_user_is_barber(current_user: User):
    role = current_user.role.value if hasattr(current_user.role, "value") else current_user.role

    if role != "barber":
        raise HTTPException(status_code=403, detail="User is not a barber")


@router.post("/")
def create_barber(
    name: str,
    active: bool = True,
    db: Session = Depends(get_db)
):
    barber = Barber(name=name, active=active)
    db.add(barber)
    db.commit()
    db.refresh(barber)
    return barber


@router.get("/")
def get_barbers(db: Session = Depends(get_db)):
    barbers = db.query(Barber).all()
    return barbers


@router.get("/available")
def get_available_barbers(db: Session = Depends(get_db)):
    barbers = (
        db.query(Barber)
        .filter(
            Barber.active.is_(True),
            Barber.user_id.isnot(None),
            Barber.price.isnot(None)
        )
        .all()
    )

    return barbers


@router.get("/me", response_model=BarberProfileRead)
def get_my_barber_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ensure_user_is_barber(current_user)

    barber = db.query(Barber).filter(Barber.user_id == current_user.id).first()

    if not barber:
        raise HTTPException(status_code=404, detail="Barber profile not found")

    return barber


@router.put("/me", response_model=BarberProfileRead)
def update_my_barber_profile(
    profile_data: BarberProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ensure_user_is_barber(current_user)

    barber = db.query(Barber).filter(Barber.user_id == current_user.id).first()

    if not barber:
        default_name = profile_data.name or current_user.email

        barber = Barber(
            user_id=current_user.id,
            name=default_name,
            active=True
        )

        db.add(barber)
        db.commit()
        db.refresh(barber)

    update_data = profile_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if hasattr(barber, field):
            setattr(barber, field, value)

    db.commit()
    db.refresh(barber)

    return barber