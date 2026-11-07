import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.affiliate import AffiliateProfile
from app.models.user import User
from app.routes.auth import get_current_user


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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    affiliate_profile = (
        db.query(AffiliateProfile)
        .filter(
            AffiliateProfile.user_id == current_user.id
        )
        .first()
    )

    if affiliate_profile is None:
        raise HTTPException(
            status_code=404,
            detail="This account does not have an affiliate profile",
        )

    personal_link = (
        f"{FRONTEND_URL}/"
        f"?ref={affiliate_profile.referral_code}"
    )

    return {
        "user_id": current_user.id,
        "owner_type": affiliate_profile.owner_type.value,
        "referral_code": affiliate_profile.referral_code,
        "personal_link": personal_link,
        "status": affiliate_profile.status.value,
    }