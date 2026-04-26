from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.barber import Barber

router = APIRouter(
    prefix="/barbers",
    tags=["Barbers"]
)

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
    