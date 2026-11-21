
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
