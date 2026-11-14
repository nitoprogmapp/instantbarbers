import secrets
import string

from sqlalchemy.orm import Session

from app.models.affiliate import (
    AffiliateOwnerType,
    AffiliateProfile,
    ReferralAttribution,
    ReferralStatus,
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


def mask_email(email: str | None):
    if not email or "@" not in email:
        return "InstantBarbers user"

    local_part, domain = email.split("@", 1)

    if len(local_part) <= 1:
        masked_local_part = "*"
    else:
        masked_local_part = (
            local_part[0]
            + "*" * min(len(local_part) - 1, 5)
        )

    return f"{masked_local_part}@{domain}"


def get_referred_user_name(user: User):
    if user.role == UserRole.client and user.client:
        client_name = getattr(user.client, "name", None)

        if client_name:
            return client_name

    if user.role == UserRole.barber and user.barber:
        barber_name = getattr(user.barber, "name", None)

        if barber_name:
            return barber_name

    return mask_email(user.email)


def get_referral_progress(
    db: Session,
    user: User,
):
    affiliate_profile = (
        db.query(AffiliateProfile)
        .filter(
            AffiliateProfile.user_id == user.id
        )
        .first()
    )

    if affiliate_profile is None:
        return None

    attributions = (
        db.query(ReferralAttribution)
        .filter(
            ReferralAttribution.referrer_profile_id
            == affiliate_profile.id
        )
        .order_by(ReferralAttribution.created_at.desc())
        .all()
    )

    total_referrals = len(attributions)

    active_referrals = sum(
        1
        for attribution in attributions
        if attribution.status == ReferralStatus.active
    )

    inactive_referrals = (
        total_referrals - active_referrals
    )

    if total_referrals:
        active_percentage = round(
            (active_referrals / total_referrals) * 100,
            1,
        )
    else:
        active_percentage = 0.0

    referrals = []

    for attribution in attributions:
        referred_user = attribution.referred_user

        is_active = (
            attribution.status == ReferralStatus.active
        )

        referrals.append(
            {
                "referral_id": attribution.id,
                "name": get_referred_user_name(
                    referred_user
                ),
                "role": attribution.referred_role.value,
                "status": (
                    "active"
                    if is_active
                    else "inactive"
                ),
                "registered_at": attribution.created_at,
                "activated_at": attribution.activated_at,
            }
        )

    return {
        "user_role": affiliate_profile.owner_type.value,
        "total_referrals": total_referrals,
        "active_referrals": active_referrals,
        "inactive_referrals": inactive_referrals,
        "progress": {
            "active_percentage": active_percentage,
        },
        "referrals": referrals,
    }
