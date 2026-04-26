from fastapi import APIRouter, HTTPException
from app.database import SessionLocal
from app.models.review import Review
from app.models.booking import Booking, BookingStatus

router = APIRouter(prefix="/reviews", tags=["Reviews"])

@router.post("/")
def create_review(booking_id: int, rating: int, comment: str):
    db = SessionLocal()

    booking = db.query(Booking).get(booking_id)
    if not booking or booking.status != BookingStatus.completed:
        raise HTTPException(status_code=400, detail="Booking not completed")

    review = Review(
        booking_id=booking_id,
        rating=rating,
        comment=comment
    )

    db.add(review)
    db.commit()
    return review
