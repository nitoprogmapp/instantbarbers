from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.database import Base


class BarberDirectory(Base):
    __tablename__ = "barber_directory"

    id = Column(Integer, primary_key=True)
    entry_key = Column(String(64), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    address = Column(String(500), nullable=False)
    phone = Column(String(20), nullable=False)
    sector = Column(String(150), nullable=False)
    sector_key = Column(String(150), nullable=False, index=True)
    is_listed = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
