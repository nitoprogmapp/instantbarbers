import os

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.affiliate import AffiliateProfile
from app.models.user import User
from app.routes.auth import get_current_user
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


router = APIRouter(
    prefix="/affiliates",
    tags=["Affiliates"],
)


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