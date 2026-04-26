from sqlalchemy import Column, Integer, ForeignKey, String
from app.database import Base

class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"))
    rating = Column(Integer)
    comment = Column(String)
    