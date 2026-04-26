from sqlalchemy import Column, Integer, String, Float, ForeignKey
from app.database import Base

class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True)
    barber_id = Column(Integer, ForeignKey("barbers.id"))
    name = Column(String)
    price = Column(Float)
    duration_minutes = Column(Integer)
    