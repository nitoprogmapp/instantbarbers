from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.affiliate import (
    AffiliateOwnerType,
    AffiliateProfile,
    AffiliateStatus,
    ReferralAttribution,
    ReferralStatus,
)
from app.models.barber import Barber
from app.models.booking import Booking, BookingStatus
from app.models.payment_attempt import PaymentAttempt
from app.models.payment_connection import PaymentConnection
from app.services.affiliate_rules import evaluate_affiliate_requirements
from app.services.affiliate_commission_service import (
    record_completed_booking_commission,
)
from app.services.affiliate_settlement_service import (
    settle_third_month_commissions,
)


AFFILIATE_ENVIRONMENT = "production"


def qualifying_haircuts(
    db,
    *,
    client_id=None,
    barber_id=None,
    now=None,
):
    if (client_id is None) == (barber_id is None):
        raise ValueError(
            "Specify exactly one client or barber"
        )

    now = now or datetime.utcnow()

    query = db.query(
        func.min(Booking.completed_at),
        func.max(Booking.completed_at),
    ).join(
        PaymentAttempt,
        PaymentAttempt.booking_id == Booking.id,
    ).filter(
        Booking.status == BookingStatus.completed,
        Booking.completed_at.isnot(None),
        Booking.completed_at <= now,
        PaymentAttempt.status == "completed",
        PaymentAttempt.environment == AFFILIATE_ENVIRONMENT,
        PaymentAttempt.payment_id.isnot(None),
        PaymentAttempt.payment_id != "",
        PaymentAttempt.amount_cents > 0,
        PaymentAttempt.currency == "CAD",
        PaymentAttempt.client_id == Booking.client_id,
        PaymentAttempt.barber_id == Booking.barber_id,
    )

    if client_id is not None:
        query = query.filter(
            Booking.client_id == client_id
        )
    else:
        query = query.filter(
            Booking.barber_id == barber_id
        )

    return query.one()


def barber_requirements(db, user_id, now):
    barber = db.query(Barber).filter(
        Barber.user_id == user_id
    ).first()

    first, last = None, None
    connected = False

    if barber is not None:
        first, last = qualifying_haircuts(
            db,
            barber_id=barber.id,
            now=now,
        )

        connected = db.query(
            PaymentConnection.id
        ).filter(
            PaymentConnection.barber_id == barber.id,
            PaymentConnection.provider == "square",
            PaymentConnection.environment == AFFILIATE_ENVIRONMENT,
            PaymentConnection.status == "connected",
            PaymentConnection.access_token_encrypted.isnot(None),
            PaymentConnection.access_token_encrypted != "",
            PaymentConnection.merchant_id.isnot(None),
            PaymentConnection.merchant_id != "",
            PaymentConnection.location_id.isnot(None),
            PaymentConnection.location_id != "",
        ).first() is not None

    return first, last, connected


def has_qualified_referred_barber(
    db,
    profile_id,
    now,
):
    profiles = db.query(
        AffiliateProfile
    ).join(
        ReferralAttribution,
        ReferralAttribution.referred_user_id
        == AffiliateProfile.user_id,
    ).filter(
        ReferralAttribution.referrer_profile_id
        == profile_id,
        ReferralAttribution.referred_role
        == AffiliateOwnerType.barber,
        ReferralAttribution.status
        != ReferralStatus.disqualified,
        AffiliateProfile.owner_type
        == AffiliateOwnerType.barber,
        AffiliateProfile.status
        != AffiliateStatus.suspended,
    ).all()

    for profile in profiles:
        first, last, connected = barber_requirements(
            db,
            profile.user_id,
            now,
        )

        if connected and first is not None:
            return True

    return False


def refresh_affiliate_users(
    db: Session,
    user_ids,
    now=None,
):
    """
    Actualiza los perfiles indicados y resuelve
    sus ingresos condicionales del tercer mes.

    El código que llama esta función controla
    el commit o rollback.

    No contacta Square ni realiza transferencias.
    """
    now = now or datetime.utcnow()

    ids = sorted({
        value
        for value in user_ids
        if value is not None
    })

    if not ids:
        return {}

    db.flush()

    profiles = db.query(
        AffiliateProfile
    ).filter(
        AffiliateProfile.user_id.in_(ids),
    ).order_by(
        AffiliateProfile.id
    ).populate_existing().with_for_update().all()

    results = {}

    for profile in profiles:
        attribution = db.query(
            ReferralAttribution
        ).filter(
            ReferralAttribution.referred_user_id
            == profile.user_id,
        ).first()

        referrer_type = None

        if attribution is not None:
            referrer = db.query(
                AffiliateProfile
            ).filter(
                AffiliateProfile.id
                == attribution.referrer_profile_id,
            ).first()

            if referrer is not None:
                referrer_type = referrer.owner_type.value

        owner_type = profile.owner_type.value
        connected = False
        referred_barber = False

        if owner_type == "barber":
            first, last, connected = barber_requirements(
                db,
                profile.user_id,
                now,
            )
        else:
            first, last = qualifying_haircuts(
                db,
                client_id=profile.user_id,
                now=now,
            )

            if referrer_type != "barber":
                referred_barber = has_qualified_referred_barber(
                    db,
                    profile.id,
                    now,
                )

        evaluation = evaluate_affiliate_requirements(
            owner_type=owner_type,
            referrer_type=referrer_type,
            first_valid_haircut_at=first,
            last_valid_haircut_at=last,
            square_connected=connected,
            has_active_referred_barber=referred_barber,
            suspended=(
                profile.status
                == AffiliateStatus.suspended
            ),
            now=now,
        )

        profile.last_qualifying_haircut_at = last
        profile.status = AffiliateStatus(
            evaluation["status"]
        )

        if (
            evaluation["status"] == "active"
            and profile.activated_at is None
        ):
            profile.activated_at = now

        if (
            attribution is not None
            and attribution.status
            != ReferralStatus.disqualified
        ):
            if evaluation["status"] == "active":
                attribution.status = ReferralStatus.active

                if attribution.activated_at is None:
                    attribution.activated_at = now

            elif (
                evaluation["status"] == "pending"
                and attribution.activated_at is None
            ):
                attribution.status = ReferralStatus.pending

            else:
                attribution.status = ReferralStatus.inactive

        settle_third_month_commissions(
            db,
            profile,
            now=now,
        )

        results[profile.user_id] = evaluation

    db.flush()

    return results


def refresh_dashboard_affiliates(
    db: Session,
    user_id,
):
    profile = db.query(
        AffiliateProfile
    ).filter(
        AffiliateProfile.user_id == user_id,
    ).first()

    if profile is None:
        return {}

    referred_ids = db.query(
        ReferralAttribution.referred_user_id
    ).filter(
        ReferralAttribution.referrer_profile_id
        == profile.id,
    ).all()

    return refresh_affiliate_users(
        db,
        [user_id] + [
            row[0]
            for row in referred_ids
        ],
    )


def refresh_after_completed_booking(
    db: Session,
    booking,
):
    user_ids = {booking.client_id}

    barber = db.query(Barber).filter(
        Barber.id == booking.barber_id
    ).first()

    if (
        barber is not None
        and barber.user_id is not None
    ):
        user_ids.add(barber.user_id)

    referrers = db.query(
        AffiliateProfile.user_id
    ).join(
        ReferralAttribution,
        ReferralAttribution.referrer_profile_id
        == AffiliateProfile.id,
    ).filter(
        ReferralAttribution.referred_user_id.in_(
            user_ids
        )
    ).all()

    user_ids.update(
        row[0]
        for row in referrers
    )

    evaluations = refresh_affiliate_users(
        db,
        user_ids,
    )

    record_completed_booking_commission(
        db,
        booking,
        evaluations,
    )

    return evaluations