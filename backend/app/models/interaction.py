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
    session_id = Column(String(100), index=True, nullable=True)
    character_id = Column(Integer, nullable=True)  # 角色ID，暂时不添加外键约束（因为Character表还未同步）
    query_text = Column(Text, nullable=True)
    response_text = Column(Text, nullable=True)
    attraction_id = Column(Integer, ForeignKey("attractions.id"), nullable=True)
    interaction_type = Column(String(50), nullable=True)  # voice_query, text_query, recommendation
    created_at = Column(DateTime(timezone=True), server_default=func.now())

