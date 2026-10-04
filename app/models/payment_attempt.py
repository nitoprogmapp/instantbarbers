from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from app.database import Base


# An attempt is committed BEFORE contacting Square. Its encrypted request and
# idempotency key are reused after a timeout, reload, or process restart.
class PaymentAttempt(Base):
    __tablename__ = "payment_attempts"

    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    barber_id = Column(Integer, ForeignKey("barbers.id"), nullable=False)
    environment = Column(String, nullable=False)
    merchant_id = Column(String, nullable=False)
    location_id = Column(String, nullable=False)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String, nullable=False, default="CAD")
    idempotency_key = Column(String(45), nullable=False, unique=True)
    request_encrypted = Column(Text, nullable=True)
    payment_id = Column(String, nullable=True, unique=True)
    status = Column(String, nullable=False, default="processing", index=True)
    error_code = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


UNRESOLVED_PAYMENT_STATUSES = ("processing", "unknown", "approved", "review")


def has_unresolved_payment(db, booking_id):
    return db.query(PaymentAttempt.id).filter(
        PaymentAttempt.booking_id == booking_id,
        PaymentAttempt.status.in_(UNRESOLVED_PAYMENT_STATUSES),
    ).first() is not None
