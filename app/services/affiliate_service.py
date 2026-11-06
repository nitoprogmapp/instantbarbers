import secrets
import string

from sqlalchemy.orm import Session

from app.models.affiliate import (
    AffiliateOwnerType,
    AffiliateProfile,
)
from app.models.user import User, UserRole


CODE_CHARACTERS = (
    string.ascii_uppercase
    + string.digits
)


def get_owner_type(user: User):
    if user.role == UserRole.client:
        return AffiliateOwnerType.client

    if user.role == UserRole.barber:
        return AffiliateOwnerType.barber

    return None


def generate_unique_referral_code(
    db: Session,
    owner_type: AffiliateOwnerType,
):
    prefix = (
        "CLI"
        if owner_type == AffiliateOwnerType.client
        else "BAR"
    )

    while True:
        random_part = "".join(
            secrets.choice(CODE_CHARACTERS)
            for _ in range(8)
        )

        referral_code = f"{prefix}-{random_part}"

        existing_code = (
            db.query(AffiliateProfile)
            .filter(
                AffiliateProfile.referral_code
                == referral_code
            )
            .first()
        )

        if existing_code is None:
            return referral_code


def create_affiliate_profile(
    db: Session,
    user: User,
):
    existing_profile = (
        db.query(AffiliateProfile)
        .filter(
            AffiliateProfile.user_id == user.id
        )
        .first()
    )

    if existing_profile:
        return existing_profile

    owner_type = get_owner_type(user)

    if owner_type is None:
        return None

    referral_code = generate_unique_referral_code(
        db=db,
        owner_type=owner_type,
    )

    affiliate_profile = AffiliateProfile(
        user_id=user.id,
        owner_type=owner_type,
        referral_code=referral_code,
    )

    db.add(affiliate_profile)
    db.flush()

    return affiliate_profile