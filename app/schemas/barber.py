from typing import Optional
from pydantic import BaseModel, ConfigDict


class BarberProfileUpdate(BaseModel):
    name: Optional[str] = None
    shop_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    photo_url: Optional[str] = None
    price: Optional[int] = None
    active: Optional[bool] = None


class BarberProfileRead(BaseModel):
    id: int
    name: str
    shop_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    photo_url: Optional[str] = None
    price: Optional[int] = None
    active: bool
    stripe_account_id: Optional[str] = None
    user_id: int

    model_config = ConfigDict(from_attributes=True)