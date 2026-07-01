from sqlalchemy import Boolean, Column, Enum, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base

import enum


class UserRole(enum.Enum):
    client = "client"
    barber = "barber"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(Enum(UserRole))
    language = Column(String, default="en")

    # Indica si el usuario confirmó su dirección de correo.
    email_verified = Column(Boolean, default=False, nullable=False)

    client = relationship("Client", back_populates="user", uselist=False)
    barber = relationship("Barber", back_populates="user", uselist=False)
