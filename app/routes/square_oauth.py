import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.barber import Barber
from app.routes.auth import get_current_user


router = APIRouter(
    prefix="/payments/square",
    tags=["Square OAuth"],
)


STATE_ALGORITHM = "HS256"
STATE_EXPIRES_MINUTES = 10

SQUARE_SCOPES = [
    "MERCHANT_PROFILE_READ",
    "PAYMENTS_READ",
    "PAYMENTS_WRITE",
    "PAYMENTS_WRITE_ADDITIONAL_RECIPIENTS",
]


def get_required_environment_variable(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Missing server configuration: {name}",
        )

    return value


@router.get("/connect")
def connect_with_square(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    barber = (
        db.query(Barber)
        .filter(Barber.user_id == current_user.id)
        .first()
    )

    if barber is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only registered barbers can connect a Square account.",
        )

    square_environment = get_required_environment_variable(
        "SQUARE_ENVIRONMENT"
    ).lower()

    square_application_id = get_required_environment_variable(
        "SQUARE_APPLICATION_ID"
    )

    secret_key = get_required_environment_variable("SECRET_KEY")

    state_payload = {
        "sub": str(current_user.id),
        "barber_id": barber.id,
        "purpose": "square_oauth",
        "nonce": secrets.token_urlsafe(32),
        "exp": datetime.now(timezone.utc)
        + timedelta(minutes=STATE_EXPIRES_MINUTES),
    }

    state_token = jwt.encode(
        state_payload,
        secret_key,
        algorithm=STATE_ALGORITHM,
    )

    if square_environment == "sandbox":
        authorization_base_url = (
            "https://connect.squareupsandbox.com/oauth2/authorize"
        )
    elif square_environment == "production":
        authorization_base_url = (
            "https://connect.squareup.com/oauth2/authorize"
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Invalid SQUARE_ENVIRONMENT configuration.",
        )

    authorization_parameters = {
        "client_id": square_application_id,
        "scope": " ".join(SQUARE_SCOPES),
        "session": "false",
        "state": state_token,
    }

    authorization_url = (
        f"{authorization_base_url}?"
        f"{urlencode(authorization_parameters)}"
    )

    return {
        "authorization_url": authorization_url,
        "expires_in_minutes": STATE_EXPIRES_MINUTES,
    }
