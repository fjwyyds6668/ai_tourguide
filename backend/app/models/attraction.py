"""
景点数据模型
"""
from sqlalchemy import Column, Integer, String, Text, Float, DateTime
from sqlalchemy.sql import func
from app.core.database import Base

class Attraction(Base):
    __tablename__ = "attractions"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text)
    location = Column(String(200))
    latitude = Column(Float)
    longitude = Column(Float)
    category = Column(String(100))
    image_url = Column(String(500))
    audio_url = Column(String(500))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

