import secrets
import string

from sqlalchemy.orm import Session

from app.models.affiliate import (
    AffiliateOwnerType,
    AffiliateProfile,
    ReferralAttribution,
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


def create_referral_attribution(
    db: Session,
    referred_user: User,
    referral_code: str | None,
):
    if not referral_code:
        return None

    normalized_code = referral_code.strip().upper()

    if not normalized_code:
        return None

    referrer_profile = (
        db.query(AffiliateProfile)
        .filter(
            AffiliateProfile.referral_code
            == normalized_code
        )
        .first()
    )

    if referrer_profile is None:
        return None

    if referrer_profile.user_id == referred_user.id:
        return None

    existing_attribution = (
        db.query(ReferralAttribution)
        .filter(
            ReferralAttribution.referred_user_id
            == referred_user.id
        )
        .first()
    )

    if existing_attribution:
        return existing_attribution

    referred_role = get_owner_type(referred_user)

    if referred_role is None:
        return None

    attribution = ReferralAttribution(
        referrer_profile_id=referrer_profile.id,
        referred_user_id=referred_user.id,
        referred_role=referred_role,
        referral_code_used=referrer_profile.referral_code,
    )

    db.add(attribution)
    db.flush()

    return attribution