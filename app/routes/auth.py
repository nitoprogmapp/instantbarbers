from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.models.client import Client
from app.models.barber import Barber
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from app.services.email_service import (
    send_verification_email,
    send_password_reset_email,
)


SECRET_KEY = "secret"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
EMAIL_VERIFICATION_EXPIRE_HOURS = 24
PASSWORD_RESET_EXPIRE_MINUTES = 30
FRONTEND_URL = "https://instantbarbers.com"


router = APIRouter(
    tags=["Auth"]
)

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/token"
)


def hash_password(password: str):
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str):
    return pwd_context.verify(password, password_hash)


def create_access_token(data: dict):
    to_encode = data.copy()

    expire = datetime.utcnow() + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({
        "exp": expire
    })

    return jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


def create_email_verification_token(user_id: int):
    expire = datetime.utcnow() + timedelta(
        hours=EMAIL_VERIFICATION_EXPIRE_HOURS
    )

    payload = {
        "user_id": user_id,
        "purpose": "email_verification",
        "exp": expire
    }

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


def create_password_reset_token(user_id: int):
    expire = datetime.utcnow() + timedelta(
        minutes=PASSWORD_RESET_EXPIRE_MINUTES
    )

    payload = {
        "user_id": user_id,
        "purpose": "password_reset",
        "exp": expire
    }

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials"
    )

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = payload.get("user_id")

        if user_id is None:
            raise credentials_exception

        user_id = int(user_id)

    except (JWTError, ValueError, TypeError):
        raise credentials_exception

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if user is None:
        raise credentials_exception

    if not user.email_verified:
        raise HTTPException(
            status_code=403,
            detail="Please verify your email before accessing your account"
        )

    return user


@router.post("/register")
def register(
    data: RegisterRequest,
    db: Session = Depends(get_db)
):
    email = str(data.email).lower().strip()

    existing_user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    new_user = User(
        email=email,
        password_hash=hash_password(data.password),
        role=data.role,
        email_verified=False
    )

    try:
        db.add(new_user)
        db.flush()

        if data.role == UserRole.client:
            new_client = Client(
                name=data.name,
                phone=data.phone,
                address=data.address,
                user_id=new_user.id
            )

            db.add(new_client)

        elif data.role == UserRole.barber:
            new_barber = Barber(
                name=data.name,
                shop_name=data.shop_name,
                phone=data.phone,
                address=data.address,
                price=data.price if data.price is not None else 4000,
                active=True,
                user_id=new_user.id
            )

            db.add(new_barber)

        verification_token = create_email_verification_token(
            new_user.id
        )

        verification_link = (
            f"{FRONTEND_URL}/verify-email"
            f"?token={verification_token}"
        )

        send_verification_email(
            to_email=new_user.email,
            verification_link=verification_link
        )

        db.commit()
        db.refresh(new_user)

    except Exception as error:
        db.rollback()

        print(
            "EMAIL REGISTRATION ERROR:",
            repr(error)
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "The account could not be created because "
                "the verification email could not be sent"
            )
        )

    return {
        "message": (
            "Registration successful. "
            "Please check your email to verify your account."
        ),
        "user_id": new_user.id,
        "role": new_user.role.value,
        "email_verified": new_user.email_verified
    }


@router.get("/verify-email")
def verify_email(
    token: str,
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = payload.get("user_id")
        purpose = payload.get("purpose")

        if user_id is None:
            raise HTTPException(
                status_code=400,
                detail="Invalid verification link"
            )

        if purpose != "email_verification":
            raise HTTPException(
                status_code=400,
                detail="Invalid verification link"
            )

        user_id = int(user_id)

    except HTTPException:
        raise

    except (JWTError, ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail="The verification link is invalid or has expired"
        )

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    if not user.email_verified:
        user.email_verified = True
        db.commit()
        db.refresh(user)

    access_token = create_access_token({
        "user_id": user.id
    })

    return {
        "message": "Email verified successfully",
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "role": user.role.value,
        "email_verified": True
    }


@router.post("/forgot-password")
def forgot_password(
    data: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    email = str(data.email).lower().strip()

    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if user:
        reset_token = create_password_reset_token(
            user.id
        )

        reset_link = (
            f"{FRONTEND_URL}/reset-password"
            f"?token={reset_token}"
        )

        try:
            send_password_reset_email(
                to_email=user.email,
                reset_link=reset_link
            )

        except Exception as error:
            print(
                "PASSWORD RESET EMAIL ERROR:",
                repr(error)
            )

            raise HTTPException(
                status_code=500,
                detail="The password reset email could not be sent"
            )

    return {
        "message": (
            "If an account exists with this email, "
            "a password reset link has been sent."
        )
    }


@router.post("/reset-password")
def reset_password(
    data: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(
            data.token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = payload.get("user_id")
        purpose = payload.get("purpose")

        if user_id is None:
            raise HTTPException(
                status_code=400,
                detail="Invalid password reset link"
            )

        if purpose != "password_reset":
            raise HTTPException(
                status_code=400,
                detail="Invalid password reset link"
            )

        user_id = int(user_id)

    except HTTPException:
        raise

    except (JWTError, ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail="The password reset link is invalid or has expired"
        )

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    user.password_hash = hash_password(
        data.new_password
    )

    db.commit()

    return {
        "message": "Password reset successfully"
    }


@router.post("/login")
def login(
    data: LoginRequest,
    db: Session = Depends(get_db)
):
    email = str(data.email).lower().strip()

    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if not user or not verify_password(
        data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    if not user.email_verified:
        raise HTTPException(
            status_code=403,
            detail="Please verify your email before logging in"
        )

    token = create_access_token({
        "user_id": user.id
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "role": user.role.value
    }


@router.post("/token")
def login_for_swagger(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    email = form_data.username.lower().strip()

    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if not user or not verify_password(
        form_data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    if not user.email_verified:
        raise HTTPException(
            status_code=403,
            detail="Please verify your email before logging in"
        )

    token = create_access_token({
        "user_id": user.id
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "role": user.role.value
    }