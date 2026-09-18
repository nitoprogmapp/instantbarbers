from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)

from app.database import Base


class PaymentConnection(Base):
    __tablename__ = "payment_connections"

    __table_args__ = (
        UniqueConstraint(
            "barber_id",
            "provider",
            "environment",
            name="uq_barber_payment_provider_environment",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    barber_id = Column(
        Integer,
        ForeignKey("barbers.id"),
        nullable=False,
        index=True,
    )

    provider = Column(
        String,
        nullable=False,
        default="square",
    )

    environment = Column(
        String,
        nullable=False,
        default="sandbox",
    )

    merchant_id = Column(
        String,
        nullable=True,
        index=True,
    )

    location_id = Column(
        String,
        nullable=True,
    )

    access_token_encrypted = Column(
        Text,
        nullable=True,
    )

    refresh_token_encrypted = Column(
        Text,
        nullable=True,
    )

    token_expires_at = Column(
        DateTime,
        nullable=True,
    )

    status = Column(
        String,
        nullable=False,
        default="pending",
    )

    connected_at = Column(
        DateTime,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )