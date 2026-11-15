from calendar import monthrange
from datetime import datetime, timezone


def utc_naive(value):
    if value is None:
        return None

    if value.tzinfo is not None:
        return value.astimezone(
            timezone.utc
        ).replace(tzinfo=None)

    return value


def add_calendar_months(value, months):
    value = utc_naive(value)

    month_index = (
        value.year * 12
        + value.month
        - 1
        + months
    )

    year, month = divmod(month_index, 12)
    month += 1

    return value.replace(
        year=year,
        month=month,
        day=min(
            value.day,
            monthrange(year, month)[1],
        ),
    )


def evaluate_affiliate_requirements(
    *,
    owner_type,
    referrer_type=None,
    first_valid_haircut_at=None,
    last_valid_haircut_at=None,
    square_connected=False,
    has_active_referred_barber=False,
    suspended=False,
    now=None,
):
    """
    Evalúa requisitos usando datos verificados por el backend.

    No contacta Square, no modifica la base de datos
    y no registra ni elimina dinero.

    Un corte válido debe estar pagado en producción
    y completado.

    El tercer mes es condicional. Su estado activo
    no autoriza por sí solo el pago de sus comisiones.
    """
    if owner_type not in ("client", "barber"):
        raise ValueError(
            "Unsupported affiliate owner type"
        )

    if referrer_type not in (
        None,
        "client",
        "barber",
    ):
        raise ValueError(
            "Unsupported referrer type"
        )

    now = (
        utc_naive(now)
        if now is not None
        else datetime.utcnow()
    )

    first = utc_naive(
        first_valid_haircut_at
    )

    last = utc_naive(
        last_valid_haircut_at
    )

    if (first is None) != (last is None):
        raise ValueError(
            "Both first and last haircut dates "
            "are required"
        )

    if first is not None and (
        first > last or last > now
    ):
        raise ValueError(
            "Invalid qualifying haircut dates"
        )

    missing = []

    needs_barber = (
        owner_type == "client"
        and referrer_type != "barber"
    )

    if first is None:
        missing.append(
            "first_paid_completed_haircut"
        )

    if (
        owner_type == "barber"
        and not square_connected
    ):
        missing.append(
            "square_connection"
        )

    if (
        needs_barber
        and not has_active_referred_barber
    ):
        missing.append(
            "active_referred_barber"
        )

    protected_until = None
    third_month_ends_at = None
    activity_period = "not_started"

    if owner_type == "barber":
        if not missing:
            activity_period = (
                "no_haircut_renewal_required"
            )

    elif last is not None:
        protected_until = add_calendar_months(
            last,
            2,
        )

        third_month_ends_at = add_calendar_months(
            last,
            3,
        )

        if now < protected_until:
            activity_period = (
                "first_two_months"
            )

        elif now < third_month_ends_at:
            activity_period = (
                "conditional_third_month"
            )

        else:
            activity_period = "expired"

    requirements_met = not missing

    if suspended:
        status = "suspended"

    elif not requirements_met:
        status = "pending"

    elif activity_period == "expired":
        status = "inactive"

    else:
        status = "active"

    return {
        "status": status,
        "requirements_met": requirements_met,
        "missing_requirements": missing,
        "requires_referred_barber": needs_barber,
        "activity_period": activity_period,
        "last_qualifying_haircut_at": last,
        "protected_until": protected_until,
        "third_month_ends_at": third_month_ends_at,
        "needs_new_haircut": (
            owner_type == "client"
            and activity_period == "expired"
        ),
        "third_month_income_conditional": (
            activity_period
            == "conditional_third_month"
        ),
    }
