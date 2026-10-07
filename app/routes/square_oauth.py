import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.barber import Barber
from app.models.payment_connection import PaymentConnection
from app.routes.auth import get_current_user
from app.routes.square_token_refresh import renew_if_due
router = APIRouter(
    prefix="/payments/square",
    tags=["Square OAuth"],
)
STATE_ALGORITHM = "HS256"
STATE_EXPIRES_MINUTES = 10
SQUARE_API_VERSION = "2026-08-19"
SQUARE_DASHBOARD_URL = "https://instantbarbers.com/barber/dashboard"
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
        "response_type": "code",
        "scope": " ".join(SQUARE_SCOPES),
        "session": "true" if square_environment == "sandbox" else "false",
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
def complete_square_oauth(
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
    square_redirect_url = get_required_environment_variable("SQUARE_REDIRECT_URL")
    token_request = {
        "client_id": square_application_id,
        "client_secret": square_application_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": square_redirect_url,
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
    try:
        token_data = token_response.json()
        if not isinstance(token_data, dict):
            raise ValueError("Invalid response")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Square returned an invalid OAuth response.",
        ) from exc
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
    try:
        locations = locations_response.json().get("locations", [])
        if not isinstance(locations, list) or any(
            not isinstance(location, dict) for location in locations
        ):
            raise ValueError("Invalid locations")
    except (ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Square returned an invalid location response.",
        ) from exc
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
    payment_connection.connected_at = datetime.now(timezone.utc).replace(tzinfo=None)
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
@router.get("/status")
def square_connection_status(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    barber = db.query(Barber).filter(Barber.user_id == current_user.id).first()
    if barber is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only registered barbers can view a Square connection.",
        )
    environment = get_required_environment_variable("SQUARE_ENVIRONMENT").lower()
    get_square_base_url(environment)
    connection = (
        db.query(PaymentConnection)
        .filter(
            PaymentConnection.barber_id == barber.id,
            PaymentConnection.provider == "square",
            PaymentConnection.environment == environment,
        )
        .first()
    )
    if connection and connection.status == "connected":
        renew_if_due(db, connection)
    expired = bool(
        connection and connection.status == "connected"
        and (not connection.token_expires_at or
             connection.token_expires_at <= datetime.now(timezone.utc).replace(tzinfo=None))
    )
    connected = bool(
        connection
        and connection.status == "connected"
        and connection.merchant_id
        and connection.location_id
        and connection.access_token_encrypted
        and connection.refresh_token_encrypted
        and not expired
    )
    return {
        "provider": "square",
        "environment": environment,
        "connected": connected,
        "status": "expired" if expired else connection.status if connection else "not_connected",
    }
@router.get("/oauth/callback")
def square_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    db: Session = Depends(get_db),
):
    # Return only a fixed outcome, never Square tokens, codes, or error details.
    try:
        complete_square_oauth(
            code=code,
            state=state,
            error=error,
            error_description=error_description,
            db=db,
        )
    except HTTPException as exc:
        db.rollback()
        if exc.detail == "Invalid or expired Square OAuth state.":
            reason = "expired_or_invalid_state"
        elif error:
            reason = "authorization_denied"
        elif exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            reason = "configuration_error"
        else:
            reason = "connection_failed"
        query = urlencode({"square": "error", "square_error": reason})
    except SQLAlchemyError:
        db.rollback()
        query = urlencode({"square": "error", "square_error": "save_failed"})
    else:
        query = urlencode({"square": "connected"})
    return RedirectResponse(
        url=f"{SQUARE_DASHBOARD_URL}?{query}",
        status_code=status.HTTP_303_SEE_OTHER,
    )