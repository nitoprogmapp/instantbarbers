from sqlalchemy import Column, Integer, ForeignKey, String, Enum, DateTime
from app.database import Base
import enum
from datetime import datetime

class BookingStatus(enum.Enum):
    pending = "pending"
    accepted = "accepted"
    paid = "paid"
    completed = "completed"
    cancelled = "cancelled"

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("users.id"))
    barber_id = Column(Integer, ForeignKey("barbers.id"))
    service_id = Column(Integer, ForeignKey("services.id"))

    status = Column(Enum(BookingStatus), default=BookingStatus.pending)
    payment_intent_id = Column(String, nullable=True)

    # ⬇️ NUEVAS COLUMNAS (IMPORTANTE)
    created_at = Column(DateTime, default=datetime.utcnow)
    accepted_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    
    