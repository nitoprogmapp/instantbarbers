from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Request
from sqlalchemy.orm import Session
from pathlib import Path
import uuid

from app.database import get_db
from app.models.barber import Barber
from app.models.user import User
from app.routes.auth import get_current_user
from app.schemas.barber import BarberProfileRead, BarberProfileUpdate


router = APIRouter(
    prefix="/barbers",
    tags=["Barbers"]
)


UPLOAD_DIR = Path("uploads/barber_photos")

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def ensure_user_is_barber(current_user: User):
    role = current_user.role.value if hasattr(current_user.role, "value") else current_user.role

    if role != "barber":
        raise HTTPException(status_code=403, detail="User is not a barber")


def get_or_create_barber_profile(db: Session, current_user: User) -> Barber:
    barber = db.query(Barber).filter(Barber.user_id == current_user.id).first()

    if not barber:
        barber = Barber(
            user_id=current_user.id,
            name=current_user.email,
            active=True
        )

        db.add(barber)
        db.commit()
        db.refresh(barber)

    return barber


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

    barber = get_or_create_barber_profile(db, current_user)

    update_data = profile_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if hasattr(barber, field):
            setattr(barber, field, value)

    db.commit()
    db.refresh(barber)

    return barber


@router.post("/me/photo", response_model=BarberProfileRead)
async def upload_my_barber_photo(
    request: Request,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ensure_user_is_barber(current_user)

    barber = get_or_create_barber_profile(db, current_user)

    content_type = photo.content_type or ""

    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid image type. Only JPG, PNG, and WEBP are allowed."
        )

    file_extension = ALLOWED_IMAGE_TYPES[content_type]

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    filename = f"barber_{barber.id}_{uuid.uuid4().hex}{file_extension}"
    file_path = UPLOAD_DIR / filename

    image_bytes = await photo.read()

    max_size_mb = 5
    if len(image_bytes) > max_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large. Maximum size is {max_size_mb}MB."
        )

    with open(file_path, "wb") as buffer:
        buffer.write(image_bytes)

    base_url = str(request.base_url).rstrip("/")
    barber.photo_url = f"{base_url}/uploads/barber_photos/{filename}"

    db.commit()
    db.refresh(barber)

    return barber