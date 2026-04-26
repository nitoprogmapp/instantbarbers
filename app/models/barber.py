from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Barber(Base):
    __tablename__ = "barbers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    photo_url = Column(String, nullable=True)
    price = Column(Integer)
    active = Column(Boolean, default=True)

    stripe_account_id = Column(String, nullable=True)

    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="barber")
