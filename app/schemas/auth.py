from pydantic import BaseModel, EmailStr
from app.models.user import UserRole

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    role: UserRole
    name: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    role: UserRole

    class Config:
        from_attributes = True
        