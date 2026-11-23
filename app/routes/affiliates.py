
import hashlib
import os
import secrets

from datetime import datetime, timedelta

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
)
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.affiliate import (
    AffiliateProfile,
    AffiliatePortalTicket,
)
from app.models.user import User
from app.routes.auth import (
    ALGORITHM,
    SECRET_KEY,
    get_current_user,
    oauth2_scheme,
)
from app.services.affiliate_service import (
    get_referral_progress,
)
from app.services.affiliate_activation_service import (
    refresh_affiliate_users,
    refresh_dashboard_affiliates,
)


FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "https://instantbarbers.com",
).rstrip("/")

AFFILIATE_PORTAL_URL = (
    "https://afiliados.instantbarbers.com"
)

PORTAL_TICKET_SECONDS = 90
PORTAL_TOKEN_HOURS = 24


router = APIRouter(
    prefix="/affiliates",
    tags=["Affiliates"],
)


class PortalExchangeRequest(BaseModel):
    ticket: str = Field(
        min_length=32,
        max_length=128,
    )


def hash_portal_ticket(ticket: str):
    return hashlib.sha256(
        ticket.encode("utf-8")
    ).hexdigest()


def get_portal_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Invalid or expired portal session",
    )

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )

        if payload.get("purpose") != "affiliate_portal":
            raise credentials_exception

        user_id = int(payload.get("user_id"))

    except (JWTError, ValueError, TypeError):
        raise credentials_exception

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if user is None or not user.email_verified:
        raise credentials_exception

    profile = (
        db.query(AffiliateProfile)
        .filter(
            AffiliateProfile.user_id == user.id
        )
        .first()
    )

    if profile is None:
        raise credentials_exception

    return user


@router.get("/me")
def get_my_affiliate_information(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"

    affiliate_profile = (
        db.query(AffiliateProfile)
        .filter(
            AffiliateProfile.user_id
            == current_user.id
        )
        .first()
    )

    if affiliate_profile is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "This account does not have "
                "an affiliate profile"
            ),
        )

    try:
        evaluations = refresh_affiliate_users(
            db,
            [current_user.id],
        )

        personal_link = (
            f"{FRONTEND_URL}/"
            f"?ref={affiliate_profile.referral_code}"
        )

        result = {
            "user_id": current_user.id,
            "owner_type": (
                affiliate_profile.owner_type.value
            ),
            "referral_code": (
                affiliate_profile.referral_code
            ),
            "personal_link": personal_link,
            "status": affiliate_profile.status.value,
            "eligibility": evaluations.get(
                current_user.id
            ),
        }

        db.commit()

    except Exception:
        db.rollback()
        raise

    return result


@router.get("/me/referrals")
def get_my_referrals(
    response: Response,
    page: int = Query(default=1, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"

    try:
        refresh_dashboard_affiliates(
            db,
            current_user.id,
        )

        referral_progress = get_referral_progress(
            db=db,
            user=current_user,
            page=page,
        )

        if referral_progress is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "This account does not have "
                    "an affiliate profile"
                ),
            )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return referral_progress


@router.post("/portal/ticket")
def create_portal_ticket(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"

    profile = (
        db.query(AffiliateProfile)
        .filter(
            AffiliateProfile.user_id
            == current_user.id
        )
        .first()
    )

    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="Affiliate profile not found",
        )

    ticket = secrets.token_urlsafe(32)

    now = datetime.utcnow()
    expires_at = now + timedelta(
        seconds=PORTAL_TICKET_SECONDS
    )

    record = AffiliatePortalTicket(
        user_id=current_user.id,
        code_hash=hash_portal_ticket(ticket),
        expires_at=expires_at,
    )

    try:
        db.add(record)
        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "portal_url": (
            f"{AFFILIATE_PORTAL_URL}/"
            f"#ticket={ticket}"
        ),
        "expires_in": PORTAL_TICKET_SECONDS,
    }


@router.post("/portal/exchange")
def exchange_portal_ticket(
    data: PortalExchangeRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"

    now = datetime.utcnow()
    ticket_hash = hash_portal_ticket(data.ticket)

    try:
        result = db.execute(
            update(AffiliatePortalTicket)
            .where(
                AffiliatePortalTicket.code_hash
                == ticket_hash,
                AffiliatePortalTicket.used_at.is_(None),
                AffiliatePortalTicket.expires_at > now,
            )
            .values(used_at=now)
            .returning(AffiliatePortalTicket.user_id)
        )

        user_id = result.scalar_one_or_none()

        if user_id is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired portal ticket",
            )

        user = (
            db.query(User)
            .filter(User.id == user_id)
            .first()
        )

        profile = (
            db.query(AffiliateProfile)
            .filter(
                AffiliateProfile.user_id == user_id
            )
            .first()
        )

        if (
            user is None
            or not user.email_verified
            or profile is None
        ):
            raise HTTPException(
                status_code=401,
                detail="Portal access denied",
            )

        portal_token = jwt.encode(
            {
                "user_id": user.id,
                "purpose": "affiliate_portal",
                "exp": now + timedelta(
                    hours=PORTAL_TOKEN_HOURS
                ),
            },
            SECRET_KEY,
            algorithm=ALGORITHM,
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "access_token": portal_token,
        "token_type": "bearer",
        "expires_in": PORTAL_TOKEN_HOURS * 3600,
        "user_role": profile.owner_type.value,
    }


@router.get("/portal/referrals")
def get_portal_referrals(
    response: Response,
    page: int = Query(default=1, ge=1),
    current_user: User = Depends(get_portal_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"

    try:
        refresh_dashboard_affiliates(
            db,
            current_user.id,
        )

        referral_progress = get_referral_progress(
            db=db,
            user=current_user,
            page=page,
        )

        if referral_progress is None:
            raise HTTPException(
                status_code=404,
                detail="Affiliate profile not found",
            )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return referral_progress


@router.get("/portal/balance")
def get_portal_balance(
    response: Response,
    current_user: User = Depends(get_portal_user),
    db: Session = Depends(get_db),
):
    from sqlalchemy import func
    from app.models.affiliate import (
        AffiliateLedger,
        LedgerEntryType,
        LedgerStatus,
    )

    response.headers["Cache-Control"] = "no-store"

    profile = (
        db.query(AffiliateProfile)
        .filter(AffiliateProfile.user_id == current_user.id)
        .first()
    )

    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="Affiliate profile not found",
        )

    totals = (
        db.query(
            AffiliateLedger.status,
            func.sum(AffiliateLedger.amount_cents),
        )
        .filter(
            AffiliateLedger.affiliate_profile_id == profile.id,
            AffiliateLedger.entry_type == LedgerEntryType.commission,
            AffiliateLedger.payout_id.is_(None),
            AffiliateLedger.status.in_([
                LedgerStatus.available,
                LedgerStatus.pending,
            ]),
        )
        .group_by(AffiliateLedger.status)
        .all()
    )

    amounts = {
        status.value: int(amount or 0)
        for status, amount in totals
    }

    available = max(0, amounts.get("available", 0))
    pending = max(0, amounts.get("pending", 0))
    minimum = 5000

    return {
        "currency": "CAD",
        "available_cents": available,
        "pending_cents": pending,
        "minimum_payout_cents": minimum,
        "missing_cents": max(0, minimum - available),
        "minimum_reached": available >= minimum,
    }

@router.get("/portal/commissions")
def get_portal_commissions(
    response: Response,
    page: int = Query(default=1, ge=1),
    current_user: User = Depends(get_portal_user),
    db: Session = Depends(get_db),
):
    from app.models.affiliate import (
        AffiliateLedger,
        LedgerEntryType,
    )

    response.headers["Cache-Control"] = "no-store"

    profile = (
        db.query(AffiliateProfile)
        .filter(AffiliateProfile.user_id == current_user.id)
        .first()
    )

    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="Affiliate profile not found",
        )

    page_size = 20

    query = db.query(AffiliateLedger).filter(
        AffiliateLedger.affiliate_profile_id == profile.id,
        AffiliateLedger.entry_type == LedgerEntryType.commission,
    )

    total = query.count()

    entries = (
        query.order_by(
            AffiliateLedger.created_at.desc(),
            AffiliateLedger.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    total_pages = max(
        1,
        (total + page_size - 1) // page_size,
    )

    return {
        "currency": "CAD",
        "commissions": [
            {
                "id": entry.id,
                "amount_cents": entry.amount_cents,
                "status": entry.status.value,
                "created_at": (
                    entry.created_at.isoformat() + "Z"
                    if entry.created_at
                    else None
                ),
            }
            for entry in entries
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_previous": page > 1,
            "has_next": page < total_pages,
        },
    }



# BLOQUE 12 — RANKING TOP 20

@router.get("/portal/ranking")
def get_portal_ranking(
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_portal_user),
):
    from sqlalchemy import func
    from app.models.affiliate import ReferralAttribution

    response.headers["Cache-Control"] = "no-store"

    count_referrals = func.count(ReferralAttribution.id)

    leaders = (
        db.query(
            AffiliateProfile.id.label("profile_id"),
            AffiliateProfile.user_id.label("user_id"),
            AffiliateProfile.owner_type.label("owner_type"),
            count_referrals.label("total_referrals"),
        )
        .join(
            ReferralAttribution,
            ReferralAttribution.referrer_profile_id
            == AffiliateProfile.id,
        )
        .group_by(
            AffiliateProfile.id,
            AffiliateProfile.user_id,
            AffiliateProfile.owner_type,
        )
        .order_by(
            count_referrals.desc(),
            AffiliateProfile.id.asc(),
        )
        .limit(20)
        .all()
    )

    users_by_id = {
        user.id: user
        for user in db.query(User)
        .filter(
            User.id.in_([row.user_id for row in leaders])
        )
        .all()
    } if leaders else {}

    ranking = []

    for position, entry in enumerate(leaders, 1):
        user = users_by_id.get(entry.user_id)
        role = entry.owner_type.value

        person = (
            user.barber if role == "barber"
            else user.client
        ) if user else None

        raw_name = str(
            getattr(person, "name", "") or ""
        ).strip()

        if raw_name and "@" not in raw_name:
            parts = raw_name.split()
            name = parts[0]

            if len(parts) > 1:
                name += f" {parts[-1][0]}."
        else:
            name = f"Affiliate #{entry.profile_id}"

        ranking.append({
            "position": position,
            "name": name,
            "total_referrals": int(entry.total_referrals),
        })

    return {"ranking": ranking}

# ACCESO AL RANKING GLOBAL DESDE LOS DASHBOARDS

@router.get("/ranking")
def get_global_ranking(
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_portal_ranking(
        response=response,
        db=db,
        current_user=current_user,
    )



# BLOQUE 14 — CONSULTAR DIRECCIÓN DE CHEQUES

@router.get("/portal/cheque-delivery")
def get_my_cheque_delivery(
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_portal_user),
):
    from app.models.affiliate import AffiliateChequeDelivery

    response.headers["Cache-Control"] = "no-store"

    profile = (
        db.query(AffiliateProfile)
        .filter(AffiliateProfile.user_id == current_user.id)
        .first()
    )

    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="Affiliate profile not found",
        )

    delivery = (
        db.query(AffiliateChequeDelivery)
        .filter(
            AffiliateChequeDelivery.affiliate_profile_id
            == profile.id
        )
        .first()
    )

    if delivery is None:
        return {
            "configured": False,
            "details": None,
        }

    return {
        "configured": True,
        "details": {
            "legal_name": delivery.legal_name,
            "address_line_1": delivery.address_line_1,
            "address_line_2": delivery.address_line_2,
            "city": delivery.city,
            "state_province": delivery.state_province,
            "postal_code": delivery.postal_code,
            "country_code": delivery.country_code,
            "phone": delivery.phone,
        },
    }



# BLOQUE 14 — VALIDACIÓN DE DATOS POSTALES

from pydantic import BaseModel, Field


class ChequeDeliveryInput(BaseModel):
    legal_name: str = Field(min_length=2, max_length=150)

    address_line_1: str = Field(min_length=3, max_length=200)
    address_line_2: str | None = Field(default=None, max_length=200)

    city: str = Field(min_length=2, max_length=100)
    state_province: str | None = Field(default=None, max_length=100)

    postal_code: str | None = Field(default=None, max_length=30)
    country_code: str = Field(pattern=r"^[A-Z]{2}$")

    phone: str | None = Field(default=None, max_length=30)

    password: str = Field(min_length=1, max_length=128)



# BLOQUE 14 — GUARDAR DIRECCIÓN DE CHEQUES

@router.put("/portal/cheque-delivery")
def save_my_cheque_delivery(
    data: ChequeDeliveryInput,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_portal_user),
):
    from app.models.affiliate import AffiliateChequeDelivery
    from app.routes.auth import verify_password

    response.headers["Cache-Control"] = "no-store"

    # Confirmar la identidad antes de modificar datos de cobro.
    if not verify_password(
        data.password,
        current_user.password_hash,
    ):
        raise HTTPException(
            status_code=403,
            detail="Incorrect password",
        )

    profile = (
        db.query(AffiliateProfile)
        .filter(AffiliateProfile.user_id == current_user.id)
        .first()
    )

    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="Affiliate profile not found",
        )

    legal_name = data.legal_name.strip()
    address_line_1 = data.address_line_1.strip()
    city = data.city.strip()

    if not legal_name or not address_line_1 or not city:
        raise HTTPException(
            status_code=422,
            detail="Required address fields cannot be empty",
        )

    delivery = (
        db.query(AffiliateChequeDelivery)
        .filter(
            AffiliateChequeDelivery.affiliate_profile_id
            == profile.id
        )
        .first()
    )

    if delivery is None:
        delivery = AffiliateChequeDelivery(
            affiliate_profile_id=profile.id
        )
        db.add(delivery)

    delivery.legal_name = legal_name
    delivery.address_line_1 = address_line_1
    delivery.address_line_2 = (
        data.address_line_2.strip()
        if data.address_line_2 else None
    )
    delivery.city = city
    delivery.state_province = (
        data.state_province.strip()
        if data.state_province else None
    )
    delivery.postal_code = (
        data.postal_code.strip()
        if data.postal_code else None
    )
    delivery.country_code = data.country_code
    delivery.phone = (
        data.phone.strip()
        if data.phone else None
    )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "saved": True,
        "message": "Cheque delivery information saved",
    }
