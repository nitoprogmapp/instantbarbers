import json
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.affiliate import (
    AffiliateLedger,
    AffiliateProfile,
    AffiliateStatus,
    LedgerEntryType,
    LedgerStatus,
    ReferralAttribution,
    ReferralStatus,
)
from app.models.booking import BookingStatus
from app.models.payment_attempt import PaymentAttempt


COMMISSION_CENTS = 500


def record_completed_booking_commission(
    db: Session,
    booking,
    affiliate_evaluations,
):
    """
    Se ejecuta después de actualizar la activación,
    dentro de la misma transacción del corte completado.

    No realiza transferencias ni contacta Square.
    No hace commit: lo controla la ruta del corte.

    Se utiliza para cortes recién completados,
    no para asignar comisiones retroactivamente.

    Los ingresos del tercer mes quedan pendientes
    hasta resolver la condición de ese período.
    """
    if (
        booking.status != BookingStatus.completed
        or booking.completed_at is None
    ):
        return None

    source_key = (
        f"affiliate:commission:booking:{booking.id}"
    )

    existing = db.query(
        AffiliateLedger
    ).filter(
        AffiliateLedger.source_key == source_key,
    ).first()

    if existing is not None:
        return existing

    payment = db.query(
        PaymentAttempt.id
    ).filter(
        PaymentAttempt.booking_id == booking.id,
        PaymentAttempt.client_id == booking.client_id,
        PaymentAttempt.barber_id == booking.barber_id,
        PaymentAttempt.environment == "production",
        PaymentAttempt.status == "completed",
        PaymentAttempt.payment_id.isnot(None),
        PaymentAttempt.payment_id != "",
        PaymentAttempt.currency == "CAD",
        PaymentAttempt.amount_cents > 0,
    ).first()

    if payment is None:
        return None

    referral = db.query(
        ReferralAttribution
    ).filter(
        ReferralAttribution.referred_user_id
        == booking.client_id,
    ).first()

    if (
        referral is None
        or referral.status == ReferralStatus.disqualified
    ):
        return None

    promoter = db.query(
        AffiliateProfile
    ).filter(
        AffiliateProfile.id
        == referral.referrer_profile_id,
    ).first()

    if (
        promoter is None
        or promoter.user_id == booking.client_id
    ):
        return None

    # La activación exigida es la del promotor,
    # tanto si es cliente como si es barbero.
    evaluation = affiliate_evaluations.get(
        promoter.user_id
    )

    if (
        promoter.status != AffiliateStatus.active
        or not evaluation
        or evaluation.get("status") != "active"
        or not evaluation.get("requirements_met")
    ):
        return None

    period = evaluation.get("activity_period")

    conditional = (
        period == "conditional_third_month"
    )

    if period not in (
        "first_two_months",
        "conditional_third_month",
        "no_haircut_renewal_required",
    ):
        return None

    now = datetime.utcnow()

    if conditional:
        deadline = evaluation.get(
            "third_month_ends_at"
        )

        last_cut = evaluation.get(
            "last_qualifying_haircut_at"
        )

        if deadline is None or last_cut is None:
            raise ValueError(
                "Missing third-month commission dates"
            )

        description = json.dumps(
            {
                "rule": "third_month_v1",
                "last_cut": last_cut.isoformat(),
                "deadline": deadline.isoformat(),
            },
            separators=(",", ":"),
        )

    else:
        description = (
            "CAD 5 commission for a direct referral haircut"
        )

    entry = AffiliateLedger(
        affiliate_profile_id=promoter.id,
        referral_id=referral.id,
        booking_id=booking.id,
        entry_type=LedgerEntryType.commission,
        amount_cents=COMMISSION_CENTS,
        status=(
            LedgerStatus.pending
            if conditional
            else LedgerStatus.available
        ),
        source_key=source_key,
        description=description,
        created_at=now,
        available_at=(
            None
            if conditional
            else now
        ),
    )

    # source_key ya es único en la base de datos.
    # Un mismo corte no puede registrar dos comisiones.
    try:
        with db.begin_nested():
            db.add(entry)
            db.flush()

    except IntegrityError:
        existing = db.query(
            AffiliateLedger
        ).filter(
            AffiliateLedger.source_key == source_key,
        ).first()

        if existing is None:
            raise

        return existing

    return entry