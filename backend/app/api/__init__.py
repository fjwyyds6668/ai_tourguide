"""
API 路由
"""
from fastapi import APIRouter
from app.api import voice, rag, attractions, admin, graph

router = APIRouter()

router.include_router(voice.router, prefix="/voice", tags=["语音"])
router.include_router(rag.router, prefix="/rag", tags=["检索"])
router.include_router(attractions.router, prefix="/attractions", tags=["景点"])
router.include_router(admin.router, prefix="/admin", tags=["管理"])
router.include_router(graph.router, prefix="/graph", tags=["图数据库"])
