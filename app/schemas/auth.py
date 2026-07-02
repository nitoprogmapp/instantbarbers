from typing import Optional

from pydantic import BaseModel, EmailStr

from app.models.user import UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    role: UserRole
    name: str

    # Datos del cliente
    phone: Optional[str] = None
    address: Optional[str] = None

    # Datos adicionales del barbero
    shop_name: Optional[str] = None
    price: Optional[int] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    role: UserRole

    class Config:
        from_attributes = True
        