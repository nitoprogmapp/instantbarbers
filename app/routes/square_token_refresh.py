"""Server-side OAuth maintenance; never creates or retries a card charge."""
import logging
import os
from datetime import datetime, timedelta, timezone
from threading import Event, Thread

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models.payment_connection import PaymentConnection

logger = logging.getLogger("uvicorn.error")
API_VERSION = "2026-08-19"
CHECK_INTERVAL_SECONDS = 3600
# Normal Square tokens last 30 days. Refresh after approximately six days,
# leaving a buffer for retries before Square's recommended seven-day cadence.
REFRESH_WINDOW = timedelta(days=24)


class TokenRefreshError(Exception):
    """A fixed, non-sensitive reason, suitable for logs and internal handling."""


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def needs_refresh(connection, now=None):
    if connection.status != "connected":
        return False
    expires = connection.token_expires_at
    return expires is None or expires <= (now or utcnow()) + REFRESH_WINDOW


def configuration(environment):
    if environment != os.getenv("SQUARE_ENVIRONMENT", "").lower():
        raise TokenRefreshError("environment_mismatch")
    urls = {
        "sandbox": "https://connect.squareupsandbox.com",
        "production": "https://connect.squareup.com",
    }
    if environment not in urls:
        raise TokenRefreshError("invalid_environment")
    app_id = os.getenv("SQUARE_APPLICATION_ID", "")
    secret = os.getenv("SQUARE_APPLICATION_SECRET", "")
    redirect = os.getenv("SQUARE_REDIRECT_URL", "")
    if not app_id or not secret or not redirect:
        raise TokenRefreshError("missing_configuration")
    if app_id.startswith("sandbox-") != (environment == "sandbox"):
        raise TokenRefreshError("application_environment_mismatch")
    try:
        cipher = Fernet(os.environ["PAYMENT_TOKEN_ENCRYPTION_KEY"].encode())
    except (KeyError, ValueError):
        raise TokenRefreshError("invalid_encryption_configuration") from None
    return urls[environment], app_id, secret, redirect, cipher


def token_request(url, payload):
    with httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
        return client.post(url + "/oauth2/token", json=payload, headers={
            "Square-Version": API_VERSION,
            "Content-Type": "application/json",
        })


def valid_response(data, merchant_id):
    if not isinstance(data, dict):
        raise TokenRefreshError("invalid_response")
    for field in ("access_token", "refresh_token", "merchant_id", "expires_at"):
        if not isinstance(data.get(field), str) or not data[field]:
            raise TokenRefreshError("incomplete_response")
    if data["merchant_id"] != merchant_id:
        raise TokenRefreshError("merchant_mismatch")
    if data.get("short_lived") is True:
        raise TokenRefreshError("unexpected_short_lived_token")
    try:
        expiry = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            raise ValueError()
        expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)
        if expiry <= utcnow() + timedelta(days=1):
            raise ValueError()
    except (TypeError, ValueError):
        raise TokenRefreshError("invalid_expiration") from None
    return expiry


def authorization_lost(response, data):
    # Do not erase credentials for generic 401/403, wrong application secrets,
    # configuration errors, rate limits, timeouts, or temporary Square failures.
    if response.status_code not in (400, 401, 403) or not isinstance(data, dict):
        return False
    if data.get("error") == "invalid_grant":
        return True
    errors = data.get("errors")
    return isinstance(errors, list) and any(
        isinstance(item, dict) and item.get("code") == "ACCESS_TOKEN_REVOKED"
        for item in errors
    )


def refresh_connection(connection_id, environment, skip_locked=False):
    """Persist tokens independently, without committing a caller's booking.

    PostgreSQL locks serialize refreshes with other refresh workers and the
    revocation webhook. Once the lock is obtained, reread status and expiration:
    never reconnect a revoked row or repeat a refresh another worker completed.
    """
    with SessionLocal() as db:
        saved = db.query(PaymentConnection).filter(
            PaymentConnection.id == connection_id,
            PaymentConnection.provider == "square",
            PaymentConnection.environment == environment,
        ).with_for_update(skip_locked=skip_locked).first()
        if not saved or saved.status != "connected":
            return "skipped"
        if not needs_refresh(saved):
            return "fresh"
        url, app_id, secret, redirect, cipher = configuration(environment)
        try:
            refresh_token = cipher.decrypt(
                (saved.refresh_token_encrypted or "").encode()
            ).decode()
            if not refresh_token:
                raise ValueError()
        except (InvalidToken, UnicodeError, ValueError):
            raise TokenRefreshError("invalid_saved_refresh_token") from None
        try:
            response = token_request(url, {
                "client_id": app_id,
                "client_secret": secret,
                "redirect_uri": redirect,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "short_lived": False,
            })
        except httpx.HTTPError:
            raise TokenRefreshError("square_temporarily_unavailable") from None
        try:
            data = response.json()
        except ValueError:
            raise TokenRefreshError("invalid_response") from None
        if response.status_code != 200:
            if authorization_lost(response, data):
                saved.status = "disconnected"
                saved.access_token_encrypted = None
                saved.refresh_token_encrypted = None
                saved.token_expires_at = None
                db.commit()
                logger.warning("Square OAuth authorization lost: connection_id=%s", connection_id)
                return "disconnected"
            raise TokenRefreshError("square_rejected_refresh")
        expiry = valid_response(data, saved.merchant_id)
        saved.access_token_encrypted = cipher.encrypt(data["access_token"].encode()).decode()
        saved.refresh_token_encrypted = cipher.encrypt(data["refresh_token"].encode()).decode()
        saved.token_expires_at = expiry
        # Preserve connected_at, merchant, location and status: this is not a
        # new seller authorization, and old revocation events must still apply.
        db.commit()
        logger.info("Square OAuth token renewed: connection_id=%s", connection_id)
        return "refreshed"


def refresh_due_connections(stop=None):
    environment = os.getenv("SQUARE_ENVIRONMENT", "").lower()
    configuration(environment)
    # Read IDs without holding locks for the entire sweep. Each row is refreshed
    # in its own transaction; one seller's failure cannot roll back other sellers.
    with SessionLocal() as db:
        ids = [row[0] for row in db.query(PaymentConnection.id).filter(
            PaymentConnection.provider == "square",
            PaymentConnection.environment == environment,
            PaymentConnection.status == "connected",
        ).order_by(PaymentConnection.id).all()]
    counts = {"refreshed": 0, "fresh": 0, "skipped": 0, "disconnected": 0, "failed": 0}
    for connection_id in ids:
        if stop is not None and stop.is_set():
            break
        try:
            outcome = refresh_connection(connection_id, environment, skip_locked=True)
            counts[outcome] += 1
        except TokenRefreshError as exc:
            counts["failed"] += 1
            logger.error("Square OAuth refresh failed: connection_id=%s reason=%s", connection_id, str(exc))
        except SQLAlchemyError:
            counts["failed"] += 1
            logger.error("Square OAuth refresh failed: connection_id=%s reason=database_error", connection_id)
    logger.info("Square OAuth maintenance: %s", counts)
    return counts


def renew_if_due(db, connection):
    """Best effort renewal when credentials are read; callers check expiry.

    A temporary failure must not discard a still-valid access token. The hourly
    worker will retry, and an expired token is never handed to the Payments API.
    """
    if not needs_refresh(connection):
        return
    try:
        refresh_connection(connection.id, connection.environment)
    except TokenRefreshError as exc:
        logger.error("Square OAuth refresh failed: connection_id=%s reason=%s", connection.id, str(exc))
        return
    except SQLAlchemyError:
        logger.error("Square OAuth refresh failed: connection_id=%s reason=database_error", connection.id)
        return
    db.refresh(connection)


def maintenance_loop(stop):
    # Run at startup and hourly while this API process is running. Event.wait
    # allows prompt shutdown, without blocking FastAPI's request/event loop.
    while not stop.is_set():
        try:
            refresh_due_connections(stop)
        except TokenRefreshError as exc:
            logger.error("Square OAuth maintenance unavailable: reason=%s", str(exc))
        except Exception:
            # Do not print exception text: HTTP/SQL exceptions can contain secrets.
            logger.error("Square OAuth maintenance failed: reason=internal_error")
        stop.wait(CHECK_INTERVAL_SECONDS)


def start_maintenance(app):
    thread = getattr(app.state, "square_refresh_thread", None)
    if thread is not None and thread.is_alive():
        return
    stop = Event()
    thread = Thread(target=maintenance_loop, args=(stop,), name="square-oauth-maintenance", daemon=True)
    app.state.square_refresh_stop = stop
    app.state.square_refresh_thread = thread
    thread.start()


def stop_maintenance(app):
    stop = getattr(app.state, "square_refresh_stop", None)
    if stop is not None:
        stop.set()
    thread = getattr(app.state, "square_refresh_thread", None)
    if thread is not None:
        thread.join(timeout=1.0)
        