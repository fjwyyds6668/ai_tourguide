"""景点 API"""
import time
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
import logging
from app.core.prisma_client import get_prisma
from sqlalchemy import func as sa_func
from app.core.database import SessionLocal
from app.models.interaction import Interaction
from app.models.user import User
from app.api.auth import get_current_user
from app.api.admin import _sync_attraction_to_graphrag, _get_prisma_model

logger = logging.getLogger(__name__)

router = APIRouter()

# 景区列表 60s 缓存
_scenic_spots_cache: Optional[list] = None
_scenic_spots_cache_time: float = 0
SCENIC_SPOTS_CACHE_TTL = 60

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
    scenic_spot_id: Optional[int] = None
    visit_count: int = 0
    created_at: Optional[datetime] = None

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

class ScenicSpotPublic(BaseModel):
    id: int
    name: str
    cover_image_url: Optional[str] = None

@router.get("", response_model=List[AttractionResponse])
@router.get("/", response_model=List[AttractionResponse])
async def get_attractions(
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None,
    scenic_spot_id: Optional[int] = None,
):
    prisma = await get_prisma()
    where: dict = {}
    if category:
        where["category"] = category
    if scenic_spot_id is not None:
        where["scenicSpotId"] = scenic_spot_id
    rows = await prisma.attraction.find_many(
        where=where or None,
        skip=skip,
        take=min(max(int(limit), 1), 500),
        order={"id": "asc"},
    )

    attraction_ids = [r.id for r in rows]
    visit_counts: dict[int, int] = {}
    if attraction_ids:
        try:
            db = SessionLocal()
            try:
                counts = (
                    db.query(Interaction.attraction_id, sa_func.count(Interaction.id).label("cnt"))
                    .filter(Interaction.attraction_id.in_(attraction_ids))
                    .group_by(Interaction.attraction_id)
                    .all()
                )
                visit_counts = {row[0]: int(row[1]) for row in counts}
            finally:
                db.close()
        except Exception as e:
            logger.warning("查询景点热度失败: %s", e)

    return [
        AttractionResponse(
            id=r.id,
            name=r.name,
            description=r.description,
            location=r.location,
            latitude=r.latitude,
            longitude=r.longitude,
            category=r.category,
            image_url=r.imageUrl,
            audio_url=r.audioUrl,
            scenic_spot_id=getattr(r, "scenicSpotId", None),
            visit_count=visit_counts.get(r.id, 0),
            created_at=getattr(r, "createdAt", None),
        )
        for r in rows
    ]

@router.get("/scenic-spots", response_model=List[ScenicSpotPublic])
async def list_scenic_spots_public():
    global _scenic_spots_cache, _scenic_spots_cache_time
    now = time.monotonic()
    if _scenic_spots_cache is not None and (now - _scenic_spots_cache_time) < SCENIC_SPOTS_CACHE_TTL:
        return _scenic_spots_cache
    prisma = await get_prisma()
    scenic_model = _get_prisma_model(prisma, "scenicspot", "scenicSpot")
    rows = await scenic_model.find_many(order={"id": "asc"}, take=1000)
    result = [
        ScenicSpotPublic(
            id=s.id,
            name=s.name,
            cover_image_url=getattr(s, "coverImageUrl", None),
        )
        for s in rows
    ]
    _scenic_spots_cache = result
    _scenic_spots_cache_time = now
    return result


@router.get("/hot", response_model=List[AttractionResponse])
async def get_hot_attractions(scenic_spot_id: Optional[int] = None, limit: int = 5):
    """返回访问热度最高的景点，基于 Interaction 表统计。"""
    limit = min(max(int(limit), 1), 20)
    try:
        db = SessionLocal()
        try:
            q = (
                db.query(Interaction.attraction_id, sa_func.count(Interaction.id).label("cnt"))
                .filter(Interaction.attraction_id.isnot(None))
                .group_by(Interaction.attraction_id)
                .order_by(sa_func.count(Interaction.id).desc())
                .limit(limit * 3)
            )
            hot_rows = q.all()
            hot_ids = [row[0] for row in hot_rows]
            visit_counts = {row[0]: int(row[1]) for row in hot_rows}
        finally:
            db.close()
    except Exception as e:
        logger.warning("查询热门景点失败: %s", e)
        hot_ids, visit_counts = [], {}

    if not hot_ids:
        return []

    prisma = await get_prisma()
    where: dict = {"id": {"in": hot_ids}}
    if scenic_spot_id is not None:
        where["scenicSpotId"] = scenic_spot_id

    rows = await prisma.attraction.find_many(where=where, take=500)

    rows.sort(key=lambda r: visit_counts.get(r.id, 0), reverse=True)
    rows = rows[:limit]

    return [
        AttractionResponse(
            id=r.id,
            name=r.name,
            description=r.description,
            location=r.location,
            latitude=r.latitude,
            longitude=r.longitude,
            category=r.category,
            image_url=r.imageUrl,
            audio_url=r.audioUrl,
            scenic_spot_id=getattr(r, "scenicSpotId", None),
            visit_count=visit_counts.get(r.id, 0),
        )
        for r in rows
    ]


def _record_attraction_visit(attraction_id: int, session_id: Optional[str] = None) -> None:
    try:
        db = SessionLocal()
        try:
            db.add(Interaction(
                session_id=session_id,
                attraction_id=attraction_id,
                interaction_type="detail_view",
            ))
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning("记录景点访问失败 attraction_id=%s: %s", attraction_id, e)


@router.get("/{attraction_id}", response_model=AttractionResponse)
async def get_attraction(
    attraction_id: int,
    background_tasks: BackgroundTasks,
    session_id: Optional[str] = None,
):
    prisma = await get_prisma()
    r = await prisma.attraction.find_unique(where={"id": attraction_id})
    if not r:
        raise HTTPException(status_code=404, detail="Attraction not found")

    background_tasks.add_task(_record_attraction_visit, attraction_id, session_id)

    visit_count = 0
    try:
        db = SessionLocal()
        try:
            visit_count = db.query(sa_func.count(Interaction.id)).filter(
                Interaction.attraction_id == attraction_id
            ).scalar() or 0
        finally:
            db.close()
    except Exception as e:
        logger.warning("查询景点热度失败: %s", e)

    return AttractionResponse(
        id=r.id,
        name=r.name,
        description=r.description,
        location=r.location,
        latitude=r.latitude,
        longitude=r.longitude,
        category=r.category,
        image_url=r.imageUrl,
        audio_url=r.audioUrl,
        scenic_spot_id=getattr(r, "scenicSpotId", None),
        visit_count=visit_count,
    )

@router.post("", response_model=AttractionResponse)
@router.post("/", response_model=AttractionResponse)
async def create_attraction(attraction: AttractionCreate, current_user: User = Depends(get_current_user)):
    prisma = await get_prisma()
    created = await prisma.attraction.create(
        data={
            "name": attraction.name,
            "description": attraction.description,
            "location": attraction.location,
            "latitude": attraction.latitude,
            "longitude": attraction.longitude,
            "category": attraction.category,
            "imageUrl": attraction.image_url,
            "audioUrl": attraction.audio_url,
        }
    )
    
    try:
        attraction_dict = {
            "id": created.id,
            "name": created.name,
            "description": created.description,
            "location": created.location,
            "latitude": created.latitude,
            "longitude": created.longitude,
            "category": created.category,
            "image_url": created.imageUrl,
            "audio_url": created.audioUrl,
            "scenic_spot_id": getattr(created, "scenicSpotId", None),
        }
        await _sync_attraction_to_graphrag(attraction_dict, operation="upsert")
    except Exception as e:
        logger.error(f"自动同步景点到 GraphRAG 失败: {e}", exc_info=True)
    return AttractionResponse(
        id=created.id,
        name=created.name,
        description=created.description,
        location=created.location,
        latitude=created.latitude,
        longitude=created.longitude,
        category=created.category,
        image_url=created.imageUrl,
        audio_url=created.audioUrl,
        scenic_spot_id=getattr(created, "scenicSpotId", None),
    )

@router.put("/{attraction_id}", response_model=AttractionResponse)
async def update_attraction(
    attraction_id: int,
    attraction: AttractionUpdate,
    current_user: User = Depends(get_current_user),
):
    prisma = await get_prisma()
    existing = await prisma.attraction.find_unique(where={"id": attraction_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Attraction not found")

    data = {}
    if attraction.name is not None:
        data["name"] = attraction.name
    if attraction.description is not None:
        data["description"] = attraction.description
    if attraction.location is not None:
        data["location"] = attraction.location
    if attraction.latitude is not None:
        data["latitude"] = attraction.latitude
    if attraction.longitude is not None:
        data["longitude"] = attraction.longitude
    if attraction.category is not None:
        data["category"] = attraction.category
    if attraction.image_url is not None:
        data["imageUrl"] = attraction.image_url
    if attraction.audio_url is not None:
        data["audioUrl"] = attraction.audio_url

    updated = await prisma.attraction.update(where={"id": attraction_id}, data=data)
    
    try:
        attraction_dict = {
            "id": updated.id,
            "name": updated.name,
            "description": updated.description,
            "location": updated.location,
            "latitude": updated.latitude,
            "longitude": updated.longitude,
            "category": updated.category,
            "image_url": updated.imageUrl,
            "audio_url": updated.audioUrl,
            "scenic_spot_id": getattr(updated, "scenicSpotId", None),
        }
        await _sync_attraction_to_graphrag(attraction_dict, operation="upsert")
    except Exception as e:
        logger.error(f"自动同步景点到 GraphRAG 失败: {e}", exc_info=True)
    return AttractionResponse(
        id=updated.id,
        name=updated.name,
        description=updated.description,
        location=updated.location,
        latitude=updated.latitude,
        longitude=updated.longitude,
        category=updated.category,
        image_url=updated.imageUrl,
        audio_url=updated.audioUrl,
        scenic_spot_id=getattr(updated, "scenicSpotId", None),
    )

@router.delete("/{attraction_id}")
async def delete_attraction(attraction_id: int, current_user: User = Depends(get_current_user)):
    prisma = await get_prisma()
    existing = await prisma.attraction.find_unique(where={"id": attraction_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Attraction not found")

    attraction_dict = {
        "id": existing.id,
        "name": existing.name,
        "description": existing.description,
        "location": existing.location,
        "latitude": existing.latitude,
        "longitude": existing.longitude,
        "category": existing.category,
        "image_url": existing.imageUrl,
        "audio_url": existing.audioUrl,
        "scenic_spot_id": getattr(existing, "scenicSpotId", None),
    }

    await prisma.attraction.delete(where={"id": attraction_id})
    
    try:
        await _sync_attraction_to_graphrag(attraction_dict, operation="delete")
    except Exception as e:
        logger.error(f"自动从 GraphRAG 删除景点失败: {e}", exc_info=True)
    return {"message": "Attraction deleted successfully"}

