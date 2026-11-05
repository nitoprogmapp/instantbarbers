import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

from app.database import Base


class AffiliateOwnerType(enum.Enum):
    client = "client"
    barber = "barber"


class AffiliateStatus(enum.Enum):
    pending = "pending"
    active = "active"
    inactive = "inactive"
    suspended = "suspended"


class ReferralStatus(enum.Enum):
    pending = "pending"
    active = "active"
    inactive = "inactive"
    disqualified = "disqualified"


class LedgerEntryType(enum.Enum):
    commission = "commission"
    refund = "refund"
    adjustment = "adjustment"
    payout = "payout"


class LedgerStatus(enum.Enum):
    pending = "pending"
    available = "available"
    paid = "paid"
    reversed = "reversed"


class PayoutStatus(enum.Enum):
    pending = "pending"
    processing = "processing"
    paid = "paid"
    failed = "failed"
    cancelled = "cancelled"


class AffiliateProfile(Base):
    __tablename__ = "affiliate_profiles"

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
        index=True,
    )

    owner_type = Column(
        Enum(
            AffiliateOwnerType,
            name="affiliate_owner_type",
        ),
        nullable=False,
    )

    referral_code = Column(
        String(32),
        unique=True,
        nullable=False,
        index=True,
    )

    status = Column(
        Enum(
            AffiliateStatus,
            name="affiliate_status",
        ),
        default=AffiliateStatus.pending,
        nullable=False,
    )

    activated_at = Column(DateTime, nullable=True)

    last_qualifying_haircut_at = Column(
        DateTime,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = relationship("User")

    referrals = relationship(
        "ReferralAttribution",
        back_populates="referrer_profile",
        foreign_keys="ReferralAttribution.referrer_profile_id",
    )

    ledger_entries = relationship(
        "AffiliateLedger",
        back_populates="affiliate_profile",
    )

    payouts = relationship(
        "AffiliatePayout",
        back_populates="affiliate_profile",
    )


class ReferralAttribution(Base):
    __tablename__ = "referral_attributions"

    id = Column(Integer, primary_key=True)

    referrer_profile_id = Column(
        Integer,
        ForeignKey("affiliate_profiles.id"),
        nullable=False,
        index=True,
    )

    referred_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
        index=True,
    )

    referred_role = Column(
        Enum(
            AffiliateOwnerType,
            name="affiliate_referred_role",
        ),
        nullable=False,
    )

    referral_code_used = Column(
        String(32),
        nullable=False,
    )

    status = Column(
        Enum(
            ReferralStatus,
            name="referral_status",
        ),
        default=ReferralStatus.pending,
        nullable=False,
    )

    activated_at = Column(DateTime, nullable=True)

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    referrer_profile = relationship(
        "AffiliateProfile",
        back_populates="referrals",
        foreign_keys=[referrer_profile_id],
    )

    referred_user = relationship(
        "User",
        foreign_keys=[referred_user_id],
    )


class AffiliatePayout(Base):
    __tablename__ = "affiliate_payouts"

    id = Column(Integer, primary_key=True)

    affiliate_profile_id = Column(
        Integer,
        ForeignKey("affiliate_profiles.id"),
        nullable=False,
        index=True,
    )

    amount_cents = Column(
        Integer,
        nullable=False,
    )

    status = Column(
        Enum(
            PayoutStatus,
            name="affiliate_payout_status",
        ),
        default=PayoutStatus.pending,
        nullable=False,
    )

    external_reference = Column(
        String(255),
        nullable=True,
    )

    requested_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    paid_at = Column(DateTime, nullable=True)

    affiliate_profile = relationship(
        "AffiliateProfile",
        back_populates="payouts",
    )

    ledger_entries = relationship(
        "AffiliateLedger",
        back_populates="payout",
    )


class AffiliateLedger(Base):
    __tablename__ = "affiliate_ledger"

    id = Column(Integer, primary_key=True)

    affiliate_profile_id = Column(
        Integer,
        ForeignKey("affiliate_profiles.id"),
        nullable=False,
        index=True,
    )

    referral_id = Column(
        Integer,
        ForeignKey("referral_attributions.id"),
        nullable=True,
        index=True,
    )

    booking_id = Column(
        Integer,
        ForeignKey("bookings.id"),
        nullable=True,
        index=True,
    )

    payout_id = Column(
        Integer,
        ForeignKey("affiliate_payouts.id"),
        nullable=True,
        index=True,
    )

    entry_type = Column(
        Enum(
            LedgerEntryType,
            name="affiliate_ledger_entry_type",
        ),
        nullable=False,
    )

    amount_cents = Column(
        Integer,
        nullable=False,
    )

    status = Column(
        Enum(
            LedgerStatus,
            name="affiliate_ledger_status",
        ),
        default=LedgerStatus.pending,
        nullable=False,
    )

    source_key = Column(
        String(150),
        unique=True,
        nullable=False,
        index=True,
    )

    description = Column(
        String(255),
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    available_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    reversed_at = Column(DateTime, nullable=True)

    affiliate_profile = relationship(
        "AffiliateProfile",
        back_populates="ledger_entries",
    )

    referral = relationship("ReferralAttribution")

    booking = relationship("Booking")

    payout = relationship(
        "AffiliatePayout",
        back_populates="ledger_entries",
    )


Index(
    "ix_referral_referrer_status",
    ReferralAttribution.referrer_profile_id,
    ReferralAttribution.status,
)

Index(
    "ix_ledger_profile_status",
    AffiliateLedger.affiliate_profile_id,
    AffiliateLedger.status,
)
