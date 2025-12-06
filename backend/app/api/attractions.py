"""
景点相关 API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from app.core.database import get_db
from app.models.attraction import Attraction

router = APIRouter()

class AttractionResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    location: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    category: Optional[str]
    image_url: Optional[str]
    audio_url: Optional[str]
    
    class Config:
        from_attributes = True

class AttractionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    audio_url: Optional[str] = None

@router.get("/", response_model=List[AttractionResponse])
async def get_attractions(
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取景点列表"""
    query = db.query(Attraction)
    if category:
        query = query.filter(Attraction.category == category)
    attractions = query.offset(skip).limit(limit).all()
    return attractions

@router.get("/{attraction_id}", response_model=AttractionResponse)
async def get_attraction(attraction_id: int, db: Session = Depends(get_db)):
    """获取单个景点详情"""
    attraction = db.query(Attraction).filter(Attraction.id == attraction_id).first()
    if not attraction:
        raise HTTPException(status_code=404, detail="Attraction not found")
    return attraction

@router.post("/", response_model=AttractionResponse)
async def create_attraction(attraction: AttractionCreate, db: Session = Depends(get_db)):
    """创建景点"""
    db_attraction = Attraction(**attraction.dict())
    db.add(db_attraction)
    db.commit()
    db.refresh(db_attraction)
    return db_attraction

@router.get("/recommendations/{user_id}")
async def get_recommendations(user_id: int, limit: int = 5, db: Session = Depends(get_db)):
    """获取个性化推荐（基于用户交互历史）"""
    # TODO: 实现基于图数据库的推荐算法
    attractions = db.query(Attraction).limit(limit).all()
    return {"recommendations": attractions}

