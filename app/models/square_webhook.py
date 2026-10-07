from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from app.database import Base


class SquareWebhookEvent(Base):
    __tablename__ = "square_webhook_events"
    __table_args__ = (UniqueConstraint("environment", "event_id", name="uq_square_webhook_event"),)

    id = Column(Integer, primary_key=True)
    environment = Column(String, nullable=False)
    event_id = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    merchant_id = Column(String, nullable=False)
    body_sha256 = Column(String(64), nullable=False)
    outcome = Column(String, nullable=False, default="received")
    payment_id = Column(String, nullable=True, index=True)
    payment_status = Column(String, nullable=True)
    app_fee_cents = Column(Integer, nullable=True)
    received_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)


class SquarePaymentRefund(Base):
    __tablename__ = "square_payment_refunds"
    __table_args__ = (UniqueConstraint("environment", "refund_id", name="uq_square_payment_refund"),)

    id = Column(Integer, primary_key=True)
    environment = Column(String, nullable=False)
    refund_id = Column(String, nullable=False)
    payment_attempt_id = Column(Integer, ForeignKey("payment_attempts.id"), nullable=True, index=True)
    payment_id = Column(String, nullable=False, index=True)
    merchant_id = Column(String, nullable=False)
    location_id = Column(String, nullable=False)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String, nullable=False)
    app_fee_cents = Column(Integer, nullable=True)
    status = Column(String, nullable=False)
    square_updated_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    