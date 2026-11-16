import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.affiliate import (
    AffiliateLedger,
    LedgerEntryType,
    LedgerStatus,
)
from app.models.booking import Booking, BookingStatus
from app.models.payment_attempt import PaymentAttempt
from app.services.affiliate_rules import (
    add_calendar_months,
    utc_naive,
)


def settle_third_month_commissions(
    db: Session,
    profile,
    now=None,
):
    """
    Resuelve únicamente los ingresos condicionales.

    No modifica ingresos disponibles, pagados
    ni cantidades que ya se hayan perdido.

    No transfiere dinero ni hace commit.

    Se llama después de bloquear el perfil
    dentro de la transacción de actualización.
    """
    now = (
        utc_naive(now)
        if now is not None
        else datetime.utcnow()
    )

    entries = db.query(
        AffiliateLedger
    ).filter(
        AffiliateLedger.affiliate_profile_id
        == profile.id,
        AffiliateLedger.entry_type
        == LedgerEntryType.commission,
        AffiliateLedger.status
        == LedgerStatus.pending,
        AffiliateLedger.source_key.like(
            "affiliate:commission:booking:%"
        ),
    ).order_by(
        AffiliateLedger.id
    ).with_for_update().all()

    result = {
        "available": 0,
        "reversed": 0,
    }

    renewals = {}

    for entry in entries:
        try:
            metadata = json.loads(
                entry.description or "{}"
            )

            if (
                not isinstance(metadata, dict)
                or metadata.get("rule")
                != "third_month_v1"
            ):
                continue

            last_cut = utc_naive(
                datetime.fromisoformat(
                    metadata["last_cut"]
                )
            )

            deadline = utc_naive(
                datetime.fromisoformat(
                    metadata["deadline"]
                )
            )

            if deadline != add_calendar_months(
                last_cut,
                3,
            ):
                continue

        except (
            ValueError,
            TypeError,
            KeyError,
            OverflowError,
        ):
            # Datos incompletos no autorizan liberar
            # ni eliminar ingresos automáticamente.
            continue

        cycle = (last_cut, deadline)

        if cycle not in renewals:
            renewals[cycle] = db.query(
                Booking.id
            ).join(
                PaymentAttempt,
                PaymentAttempt.booking_id
                == Booking.id,
            ).filter(
                Booking.client_id == profile.user_id,
                Booking.status == BookingStatus.completed,
                Booking.completed_at > last_cut,
                Booking.completed_at < deadline,
                Booking.completed_at <= now,
                PaymentAttempt.client_id
                == Booking.client_id,
                PaymentAttempt.barber_id
                == Booking.barber_id,
                PaymentAttempt.environment
                == "production",
                PaymentAttempt.status == "completed",
                PaymentAttempt.payment_id.isnot(None),
                PaymentAttempt.payment_id != "",
                PaymentAttempt.amount_cents > 0,
                PaymentAttempt.currency == "CAD",
            ).first() is not None

        if renewals[cycle]:
            entry.status = LedgerStatus.available
            entry.available_at = now
            result["available"] += 1

        elif now >= deadline:
            entry.status = LedgerStatus.reversed
            entry.reversed_at = now
            result["reversed"] += 1

    db.flush()

    return result