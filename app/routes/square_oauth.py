import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.barber import Barber
from app.models.payment_connection import PaymentConnection
from app.routes.auth import get_current_user


router = APIRouter(
    prefix="/payments/square",
    tags=["Square OAuth"],
)


STATE_ALGORITHM = "HS256"
STATE_EXPIRES_MINUTES = 10
SQUARE_API_VERSION = "2026-08-19"

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


def get_square_base_url(square_environment: str) -> str:
    if square_environment == "sandbox":
        return "https://connect.squareupsandbox.com"

    if square_environment == "production":
        return "https://connect.squareup.com"

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Invalid SQUARE_ENVIRONMENT configuration.",
    )


def encrypt_square_token(token: str) -> str:
    encryption_key = get_required_environment_variable(
        "PAYMENT_TOKEN_ENCRYPTION_KEY"
    )

    try:
        cipher = Fernet(encryption_key.encode())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Invalid payment token encryption configuration.",
        ) from exc

    return cipher.encrypt(token.encode()).decode()


def parse_square_expiration(expires_at: str) -> datetime:
    try:
        parsed_expiration = datetime.fromisoformat(
            expires_at.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Square returned an invalid token expiration date.",
        ) from exc

    return parsed_expiration.astimezone(timezone.utc).replace(
        tzinfo=None
    )


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

    square_redirect_url = get_required_environment_variable(
        "SQUARE_REDIRECT_URL"
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

    square_base_url = get_square_base_url(square_environment)

    authorization_parameters = {
        "client_id": square_application_id,
        "scope": " ".join(SQUARE_SCOPES),
        "session": "false",
        "state": state_token,
        "redirect_uri": square_redirect_url,
    }

    authorization_url = (
        f"{square_base_url}/oauth2/authorize?"
        f"{urlencode(authorization_parameters)}"
    )

    return {
        "authorization_url": authorization_url,
        "expires_in_minutes": STATE_EXPIRES_MINUTES,
    }


@router.get("/oauth/callback")
def square_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    db: Session = Depends(get_db),
):
    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Square OAuth state.",
        )

    secret_key = get_required_environment_variable("SECRET_KEY")

    try:
        state_payload = jwt.decode(
            state,
            secret_key,
            algorithms=[STATE_ALGORITHM],
        )

        if state_payload.get("purpose") != "square_oauth":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Square OAuth state purpose.",
            )

        user_id = int(state_payload["sub"])
        barber_id = int(state_payload["barber_id"])

    except HTTPException:
        raise

    except (JWTError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired Square OAuth state.",
        ) from exc

    barber = (
        db.query(Barber)
        .filter(
            Barber.id == barber_id,
            Barber.user_id == user_id,
        )
        .first()
    )

    if barber is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The barber associated with this authorization was not found.",
        )

    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Square authorization was not completed: "
                f"{error_description or error}"
            ),
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Square did not return an authorization code.",
        )

    square_environment = get_required_environment_variable(
        "SQUARE_ENVIRONMENT"
    ).lower()

    square_application_id = get_required_environment_variable(
        "SQUARE_APPLICATION_ID"
    )

    square_application_secret = get_required_environment_variable(
        "SQUARE_APPLICATION_SECRET"
    )

    square_base_url = get_square_base_url(square_environment)

    token_request = {
        "client_id": square_application_id,
        "client_secret": square_application_secret,
        "code": code,
        "grant_type": "authorization_code",
    }

    square_headers = {
        "Square-Version": SQUARE_API_VERSION,
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=20.0) as client:
            token_response = client.post(
                f"{square_base_url}/oauth2/token",
                json=token_request,
                headers=square_headers,
            )

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Square could not be reached to complete authorization.",
        ) from exc

    if token_response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Square rejected the OAuth token exchange.",
        )

    token_data = token_response.json()

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    merchant_id = token_data.get("merchant_id")
    expires_at = token_data.get("expires_at")

    if not all(
        [
            access_token,
            refresh_token,
            merchant_id,
            expires_at,
        ]
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Square returned an incomplete OAuth response.",
        )

    encrypted_access_token = encrypt_square_token(access_token)
    encrypted_refresh_token = encrypt_square_token(refresh_token)
    token_expires_at = parse_square_expiration(expires_at)

    payment_connection = (
        db.query(PaymentConnection)
        .filter(
            PaymentConnection.barber_id == barber.id,
            PaymentConnection.provider == "square",
            PaymentConnection.environment == square_environment,
        )
        .first()
    )

    if payment_connection is None:
        payment_connection = PaymentConnection(
            barber_id=barber.id,
            provider="square",
            environment=square_environment,
        )

        db.add(payment_connection)

    payment_connection.merchant_id = merchant_id
    payment_connection.location_id = None
    payment_connection.access_token_encrypted = (
        encrypted_access_token
    )
    payment_connection.refresh_token_encrypted = (
        encrypted_refresh_token
    )
    payment_connection.token_expires_at = token_expires_at
    payment_connection.status = "pending"

    db.commit()
    db.refresh(payment_connection)

    location_headers = {
        "Square-Version": SQUARE_API_VERSION,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=20.0) as client:
            locations_response = client.get(
                f"{square_base_url}/v2/locations",
                headers=location_headers,
            )

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Square authorization was saved, but the seller "
                "location could not be retrieved."
            ),
        ) from exc

    if locations_response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Square authorization was saved, but Square "
                "rejected the location request."
            ),
        )

    locations = locations_response.json().get("locations", [])

    active_locations = [
        location
        for location in locations
        if location.get("status") == "ACTIVE"
    ]

    payment_locations = [
        location
        for location in active_locations
        if "CREDIT_CARD_PROCESSING"
        in location.get("capabilities", [])
    ]

    selected_location = None

    if payment_locations:
        selected_location = payment_locations[0]
    elif active_locations:
        selected_location = active_locations[0]

    if selected_location is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Square authorization was saved, but no active "
                "seller location was found."
            ),
        )

    payment_connection.location_id = selected_location["id"]
    payment_connection.status = "connected"
    payment_connection.connected_at = datetime.utcnow()

    db.commit()
    db.refresh(payment_connection)

    return {
        "status": "connected",
        "provider": "square",
        "environment": square_environment,
        "merchant_id": payment_connection.merchant_id,
        "location_id": payment_connection.location_id,
        "message": "Square account connected successfully.",
    }