"""
历史记录查询 API
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from app.core.database import get_db
from app.models.interaction import Interaction
from pydantic import BaseModel

router = APIRouter()

class InteractionHistory(BaseModel):
    id: int
    session_id: Optional[str]
    query_text: Optional[str]
    response_text: Optional[str]
    interaction_type: Optional[str]
    created_at: str
    
    class Config:
        from_attributes = True

class HistoryListResponse(BaseModel):
    data: List[InteractionHistory]
    total: int

@router.get("/history", response_model=HistoryListResponse)
async def get_interaction_history(
    session_id: Optional[str] = Query(None, description="会话ID"),
    limit: int = Query(5, ge=1, le=100, description="返回数量限制，默认最近5条"),
    skip: int = Query(0, ge=0, description="跳过数量"),
    db: Session = Depends(get_db)
):
    """
    获取交互历史记录
    
    - 如果提供 session_id，返回该会话的所有交互记录
    - 如果不提供 session_id，返回最近的交互记录
    - 使用窗口函数一次查询同时返回 total 与当前页，减少 DB 往返
    """
    try:
        base = db.query(Interaction)
        if session_id:
            base = base.filter(Interaction.session_id == session_id)
        # COUNT(*) OVER() 在过滤集上计算，ORDER BY/OFFSET/LIMIT 之后每行仍带完整总数
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

        data = [
            InteractionHistory(
                id=interaction.id,
                session_id=interaction.session_id,
                query_text=interaction.query_text,
                response_text=interaction.response_text,
                interaction_type=interaction.interaction_type,
                created_at=interaction.created_at.isoformat() if interaction.created_at else ""
            )
            for interaction in interactions
        ]
        return HistoryListResponse(data=data, total=total)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history/{session_id}", response_model=List[InteractionHistory])
async def get_session_history(
    session_id: str,
    limit: int = Query(5, ge=1, le=200, description="返回数量限制，默认最近5条"),
    db: Session = Depends(get_db)
):
    """获取指定会话的交互记录（按时间倒序，最近在前）"""
    try:
        interactions = db.query(Interaction).filter(
            Interaction.session_id == session_id
        ).order_by(desc(Interaction.created_at)).limit(limit).all()
        
        return [
            InteractionHistory(
                id=interaction.id,
                session_id=interaction.session_id,
                query_text=interaction.query_text,
                response_text=interaction.response_text,
                interaction_type=interaction.interaction_type,
                created_at=interaction.created_at.isoformat() if interaction.created_at else ""
            )
            for interaction in interactions
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

