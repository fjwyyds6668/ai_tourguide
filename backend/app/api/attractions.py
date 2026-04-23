"""景点 API"""
import asyncio
import json
import re
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


class RecommendResponse(BaseModel):
    recommendation: Optional[str] = None
    attractions: List[AttractionResponse] = []


@router.get("/recommend", response_model=RecommendResponse)
async def get_personalized_recommendation(
    session_id: str,
    scenic_spot_id: Optional[int] = None,
):
    """根据用户对话历史，调用 LLM 生成个性化景点/路线推荐。"""
    from app.services.session_service import session_service
    from app.services.rag_service import rag_service
    from app.core.config import settings

    history = session_service.get_conversation_history(session_id)
    logger.info("推荐接口 session_id=%s history_len=%d scenic_spot_id=%s", session_id, len(history), scenic_spot_id)
    if not history:
        logger.warning("推荐空返回：session %s 无对话历史", session_id)
        return RecommendResponse()

    prisma = await get_prisma()
    where: dict = {}
    if scenic_spot_id is not None:
        where["scenicSpotId"] = scenic_spot_id
    all_attractions = await prisma.attraction.find_many(where=where, take=100)
    if not all_attractions:
        logger.warning("推荐空返回：scenic_spot_id=%s 下无景点", scenic_spot_id)
        return RecommendResponse()
    logger.info("候选景点数=%d", len(all_attractions))

    attractions_info = "\n".join([
        f"ID:{a.id} 名称:{a.name} 类别:{a.category or '未知'} 简介:{(a.description or '')[:60]}"
        for a in all_attractions
    ])

    # 阶段一：基于全部历史对话提炼用户画像
    profile_conv = "\n".join([
        f"{'游客' if m['role'] == 'user' else 'AI导游'}: {m['content']}"
        for m in history
    ])
    profile_prompt = (
        "下面是一位游客与AI导游的完整对话。请提炼该游客的旅游偏好画像，"
        "200字以内，使用结构化要点，覆盖以下维度（如对话中未涉及可省略）：\n"
        "- 偏好（景点类型、氛围、风格等）\n"
        "- 限制（身体状况、同行人员、时间预算等）\n"
        "- 明确表达的诉求或避免项\n\n"
        "只输出画像正文，不要寒暄或解释。\n\n"
        f"对话记录：\n{profile_conv}"
    )
    user_profile: Optional[str] = None
    try:
        profile_resp = await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(
                None,
                lambda: rag_service.llm_client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=[{"role": "user", "content": profile_prompt}],
                    max_tokens=300,
                    temperature=0.3,
                ),
            ),
            timeout=30.0,
        )
        if not profile_resp.choices:
            raise ValueError("LLM 返回空 choices（画像阶段）")
        user_profile = profile_resp.choices[0].message.content.strip()
        logger.info("用户画像生成成功，长度=%d", len(user_profile or ""))
    except Exception as e:
        logger.warning("用户画像生成失败，将降级为仅使用近期对话: %s", e)

    # 阶段二：画像负责长期偏好，最近 10 条对话负责当下语境
    conv_text = "\n".join([
        f"{'游客' if m['role'] == 'user' else 'AI导游'}: {m['content']}"
        for m in history[-10:]
    ])

    context_block = (
        f"用户画像（基于全部历史对话提炼）：\n{user_profile}\n\n近期对话：\n{conv_text}"
        if user_profile
        else f"对话记录：\n{conv_text}"
    )

    prompt = (
        "根据以下游客信息，分析游客的兴趣偏好，"
        "从景点列表中为其量身推荐最合适的景点或游览路线。\n\n"
        f"{context_block}\n\n"
        f"可选景点：\n{attractions_info}\n\n"
        "请以JSON格式返回，不要包含任何其他内容：\n"
        '{"recommendation": "必须严格按照以下格式输出，不得改变结构：\'根据您[列举2-4个关键偏好因素，如偏好自然景观、宁静氛围、摄影需求等]，为您推荐以下景点：[景点名称，用顿号分隔]。[说明推荐理由和建议游览顺序]\'。总字数不超过500字，只写景点名称，不要出现任何ID或数字编号。", '
        '"attraction_ids": [推荐的景点ID列表，最多5个整数]}'
    )

    try:
        resp = await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(
                None,
                lambda: rag_service.llm_client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=900,
                    temperature=0.7,
                ),
            ),
            timeout=30.0,
        )
        if not resp.choices:
            raise ValueError("LLM 返回空 choices（推荐阶段）")
        raw = resp.choices[0].message.content.strip()
        logger.info("阶段二 LLM 原始返回(前200字)=%s", raw[:200])
        # 兼容 LLM 返回 markdown 代码块的情况，用非贪心匹配取第一个完整 JSON 对象
        m = re.search(r"\{.*?\}", raw, re.DOTALL)
        if not m:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(m.group() if m else raw)
        rec_text = re.sub(r'[（(]\s*ID\s*[:：]\s*\d+\s*[）)]', '', data.get("recommendation", "")).strip()
        attraction_ids_raw = data.get("attraction_ids", [])
        if not isinstance(attraction_ids_raw, list):
            attraction_ids_raw = []
        rec_ids = set(int(i) for i in attraction_ids_raw if str(i).strip().lstrip('-').isdigit())
        logger.info("推荐解析成功 rec_text_len=%d rec_ids=%s", len(rec_text), rec_ids)
    except Exception as e:
        logger.warning("个性化推荐失败: %s | raw=%s", e, raw[:200] if 'raw' in locals() else "N/A")
        return RecommendResponse()

    rec_attractions = [a for a in all_attractions if a.id in rec_ids]
    # 保持 LLM 返回的顺序
    attraction_ids_raw = data.get("attraction_ids", []) if isinstance(data.get("attraction_ids"), list) else []
    id_order = {v: i for i, v in enumerate(attraction_ids_raw)}
    rec_attractions.sort(key=lambda a: id_order.get(a.id, 99))

    return RecommendResponse(
        recommendation=rec_text,
        attractions=[
            AttractionResponse(
                id=a.id, name=a.name, description=a.description,
                location=a.location, latitude=a.latitude, longitude=a.longitude,
                category=a.category, image_url=a.imageUrl, audio_url=a.audioUrl,
                scenic_spot_id=getattr(a, "scenicSpotId", None), visit_count=0,
            )
            for a in rec_attractions
        ],
    )


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

