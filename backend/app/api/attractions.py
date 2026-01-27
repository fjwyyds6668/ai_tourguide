"""
景点相关 API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import logging
from app.core.database import get_db
from app.models.attraction import Attraction
from app.api.admin import _sync_attraction_to_graphrag

logger = logging.getLogger(__name__)

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

class AttractionUpdate(BaseModel):
    name: Optional[str] = None
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
    """创建景点（自动同步到 GraphRAG）"""
    db_attraction = Attraction(**attraction.dict())
    db.add(db_attraction)
    db.commit()
    db.refresh(db_attraction)
    
    # 自动同步到 GraphRAG
    try:
        attraction_dict = {
            "id": db_attraction.id,
            "name": db_attraction.name,
            "description": db_attraction.description,
            "location": db_attraction.location,
            "latitude": db_attraction.latitude,
            "longitude": db_attraction.longitude,
            "category": db_attraction.category,
        }
        await _sync_attraction_to_graphrag(attraction_dict, operation="upsert")
    except Exception as e:
        logger.error(f"自动同步景点到 GraphRAG 失败: {e}", exc_info=True)
        # 不抛出异常，避免影响主流程
    
    return db_attraction

@router.put("/{attraction_id}", response_model=AttractionResponse)
async def update_attraction(
    attraction_id: int,
    attraction: AttractionUpdate,
    db: Session = Depends(get_db)
):
    """更新景点（自动同步到 GraphRAG）"""
    db_attraction = db.query(Attraction).filter(Attraction.id == attraction_id).first()
    if not db_attraction:
        raise HTTPException(status_code=404, detail="Attraction not found")
    
    # 更新字段
    update_data = attraction.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_attraction, key, value)
    
    db.commit()
    db.refresh(db_attraction)
    
    # 自动同步到 GraphRAG
    try:
        attraction_dict = {
            "id": db_attraction.id,
            "name": db_attraction.name,
            "description": db_attraction.description,
            "location": db_attraction.location,
            "latitude": db_attraction.latitude,
            "longitude": db_attraction.longitude,
            "category": db_attraction.category,
        }
        await _sync_attraction_to_graphrag(attraction_dict, operation="upsert")
    except Exception as e:
        logger.error(f"自动同步景点到 GraphRAG 失败: {e}", exc_info=True)
        # 不抛出异常，避免影响主流程
    
    return db_attraction

@router.delete("/{attraction_id}")
async def delete_attraction(attraction_id: int, db: Session = Depends(get_db)):
    """删除景点（自动从 GraphRAG 删除）"""
    db_attraction = db.query(Attraction).filter(Attraction.id == attraction_id).first()
    if not db_attraction:
        raise HTTPException(status_code=404, detail="Attraction not found")
    
    # 先获取景点信息用于删除 GraphRAG
    attraction_dict = {
        "id": db_attraction.id,
        "name": db_attraction.name,
        "description": db_attraction.description,
        "location": db_attraction.location,
        "latitude": db_attraction.latitude,
        "longitude": db_attraction.longitude,
        "category": db_attraction.category,
    }
    
    # 从数据库删除
    db.delete(db_attraction)
    db.commit()
    
    # 自动从 GraphRAG 删除
    try:
        await _sync_attraction_to_graphrag(attraction_dict, operation="delete")
    except Exception as e:
        logger.error(f"自动从 GraphRAG 删除景点失败: {e}", exc_info=True)
        # 不抛出异常，避免影响主流程
    
    return {"message": "Attraction deleted successfully"}

@router.get("/recommendations/{user_id}")
async def get_recommendations(user_id: int, limit: int = 5, db: Session = Depends(get_db)):
    """获取个性化推荐（基于用户交互历史）"""
    # TODO: 实现基于图数据库的推荐算法
    attractions = db.query(Attraction).limit(limit).all()
    return {"recommendations": attractions}

