"""
用户交互数据模型
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base

class Interaction(Base):
    __tablename__ = "interactions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_id = Column(String(100), index=True)
    query_text = Column(Text)
    response_text = Column(Text)
    attraction_id = Column(Integer, ForeignKey("attractions.id"), nullable=True)
    interaction_type = Column(String(50))  # voice_query, text_query, recommendation
    created_at = Column(DateTime(timezone=True), server_default=func.now())

