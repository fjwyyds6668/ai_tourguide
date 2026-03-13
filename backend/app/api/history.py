"""历史记录 API"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from app.core.database import get_db
from app.models.interaction import Interaction
from app.core.prisma_client import get_prisma
from pydantic import BaseModel
import logging
import asyncio

router = APIRouter()
logger = logging.getLogger(__name__)

class InteractionHistory(BaseModel):
    id: int
    session_id: Optional[str]
    query_text: Optional[str]
    response_text: Optional[str]
    interaction_type: Optional[str]
    attraction_id: Optional[int] = None
    attraction_name: Optional[str] = None
    created_at: str
    
    class Config:
        from_attributes = True

class HistoryListResponse(BaseModel):
    data: List[InteractionHistory]
    total: int

async def _resolve_attraction_names(attraction_ids: List[int]) -> dict[int, str]:
    """使用 Prisma 批量补齐景点名（表不存在/查询失败时安全降级）。"""
    ids = [int(x) for x in attraction_ids if x is not None]
    if not ids:
        return {}
    try:
        prisma = await get_prisma()
        try:
            rows = await prisma.attraction.find_many(where={"id": {"in": ids}})
            m = {int(r.id): (getattr(r, "name", "") or "") for r in (rows or []) if r and getattr(r, "id", None) is not None}
            if m:
                return m
        except Exception as e:
            logger.warning("prisma.attraction.find_many failed: %s", e)

        async def _one(aid: int):
            try:
                r = await prisma.attraction.find_unique(where={"id": int(aid)})
                if r and getattr(r, "id", None) is not None:
                    return int(r.id), (getattr(r, "name", "") or "")
            except Exception:
                return None
            return None

        pairs = await asyncio.gather(*[_one(aid) for aid in ids])
        return {k: v for kv in pairs if kv for k, v in [kv]}
    except Exception as e:
        logger.warning("resolve attraction names failed: %s", e)
        return {}

@router.get("/history", response_model=HistoryListResponse)
async def get_interaction_history(
    session_id: Optional[str] = Query(None, description="会话ID"),
    only_qa: bool = Query(False, description="仅返回问答记录（有问题/回答或交互类型为 text_query/voice_query）"),
    limit: int = Query(5, ge=1, le=100, description="返回数量限制，默认最近5条"),
    skip: int = Query(0, ge=0, description="跳过数量"),
    db: Session = Depends(get_db)
):
    try:
        base = db.query(Interaction)
        if session_id:
            base = base.filter(Interaction.session_id == session_id)
        if only_qa:
            base = base.filter(
                (Interaction.interaction_type.in_(["text_query", "voice_query"]))
                | (Interaction.query_text.isnot(None))
                | (Interaction.response_text.isnot(None))
            )
        total_col = func.count(Interaction.id).over().label("_total")
        rows = (
            base.add_columns(total_col)
            .order_by(desc(Interaction.created_at))
            .offset(skip)
            .limit(limit)
            .all()
        )
        total = int(rows[0][1]) if rows else 0
        interactions = [row[0] for row in rows]
        name_map = await _resolve_attraction_names([i.attraction_id for i in interactions if i and i.attraction_id])

        data: List[InteractionHistory] = []
        for interaction in interactions:
            data.append(
                InteractionHistory(
                    id=interaction.id,
                    session_id=interaction.session_id,
                    query_text=interaction.query_text,
                    response_text=interaction.response_text,
                    interaction_type=interaction.interaction_type,
                    attraction_id=interaction.attraction_id,
                    attraction_name=name_map.get(int(interaction.attraction_id)) if interaction.attraction_id else None,
                    created_at=interaction.created_at.isoformat() if interaction.created_at else "",
                )
            )
        return HistoryListResponse(data=data, total=total)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history/{session_id}", response_model=List[InteractionHistory])
async def get_session_history(
    session_id: str,
    only_qa: bool = Query(False, description="仅返回问答记录（有问题/回答或交互类型为 text_query/voice_query）"),
    limit: int = Query(5, ge=1, le=200, description="返回数量限制，默认最近5条"),
    db: Session = Depends(get_db)
):
    try:
        q = db.query(Interaction).filter(Interaction.session_id == session_id)
        if only_qa:
            q = q.filter(
                (Interaction.interaction_type.in_(["text_query", "voice_query"]))
                | (Interaction.query_text.isnot(None))
                | (Interaction.response_text.isnot(None))
            )
        interactions = q.order_by(desc(Interaction.created_at)).limit(limit).all()
        name_map = await _resolve_attraction_names([i.attraction_id for i in interactions if i and i.attraction_id])
        
        return [
            InteractionHistory(
                id=interaction.id,
                session_id=interaction.session_id,
                query_text=interaction.query_text,
                response_text=interaction.response_text,
                interaction_type=interaction.interaction_type,
                attraction_id=interaction.attraction_id,
                attraction_name=name_map.get(int(interaction.attraction_id)) if interaction.attraction_id else None,
                created_at=interaction.created_at.isoformat() if interaction.created_at else ""
            )
            for interaction in interactions
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

