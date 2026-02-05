"""GraphRAG 检索 API"""
import logging
import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.services.rag_service import rag_service
from app.services.session_service import session_service
from app.core.prisma_client import get_prisma
from app.models.interaction import Interaction

logger = logging.getLogger(__name__)

router = APIRouter()

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5

class QueryResponse(BaseModel):
    vector_results: List[Dict[str, Any]]
    graph_results: List[Dict[str, Any]]
    query: str

class GenerateRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    character_id: Optional[int] = None
    use_rag: bool = True

class GenerateResponse(BaseModel):
    answer: str
    query: str
    context: str = ""
    session_id: str

@router.post("/search", response_model=QueryResponse)
async def hybrid_search(request: QueryRequest):
    """混合检索"""
    try:
        results = await rag_service.hybrid_search(request.query, top_k=request.top_k)
        return QueryResponse(**results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/vector-search")
async def vector_search(request: QueryRequest):
    """向量搜索"""
    try:
        results = await rag_service.vector_search(request.query, top_k=request.top_k)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/graph-search")
async def graph_search(entity_name: str, relation_type: str = None, limit: int = 10):
    """图搜索"""
    try:
        results = await rag_service.graph_search(entity_name, relation_type, limit)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate", response_model=GenerateResponse)
async def generate_answer(request: GenerateRequest, background_tasks: BackgroundTasks):
    """生成回答（RAG + 多轮对话）。"""
    try:
        session_id = request.session_id
        if not session_id:
            session_id = session_service.create_session(request.character_id)
        else:
            session = session_service.get_session(session_id)
            if not session:
                session_id = session_service.create_session(request.character_id)
        # 并行加载角色提示词和对话历史
        async def load_character_prompt():
            if request.character_id:
                try:
                    prisma = await get_prisma()
                    character = await prisma.character.find_unique(where={"id": request.character_id})
                    if character and character.prompt:
                        return character.prompt
                except Exception as e:
                    logger.error(f"Failed to load character prompt: {e}")
            return None
        
        def load_conversation_history():
            return session_service.get_conversation_history(session_id)
        
        # 并行加载角色提示词和对话历史
        character_prompt, conversation_history = await asyncio.gather(
            load_character_prompt(),
            asyncio.to_thread(load_conversation_history)
        )
        
        result = await rag_service.generate_answer(
            query=request.query,
            context=None,
            use_rag=request.use_rag,
            conversation_history=conversation_history,
            character_prompt=character_prompt
        )
        answer = result["answer"]
        context = result.get("context", "")
        primary_attraction_id = result.get("primary_attraction_id")
        
        # 立即更新会话历史（同步操作，很快）
        session_service.add_message(session_id, "user", request.query)
        session_service.add_message(session_id, "assistant", answer)
        
        # 数据库保存使用后台任务，不阻塞响应
        def save_interaction():
            try:
                from app.core.database import SessionLocal
                from app.models.attraction import Attraction as AttractionModel
                db_local = SessionLocal()
                try:
                    aid = primary_attraction_id
                    # 若 RAG 未返回景点 ID，根据问题文本尝试按景点名称匹配（便于服务次数统计）
                    if aid is None and request.query and request.query.strip():
                        q = (request.query or "").strip()
                        rows = (
                            db_local.query(AttractionModel.id, AttractionModel.name)
                            .filter(AttractionModel.name.isnot(None), AttractionModel.name != "")
                            .limit(200)
                            .all()
                        )
                        for row in rows:
                            name = row[1] if len(row) > 1 else None
                            if name and name in q:
                                aid = row[0]
                                break
                    interaction = Interaction(
                        session_id=session_id,
                        character_id=request.character_id,
                        query_text=request.query,
                        response_text=answer,
                        interaction_type="voice_query",
                        attraction_id=aid,
                    )
                    db_local.add(interaction)
                    db_local.commit()
                finally:
                    db_local.close()
            except Exception as e:
                logger.error(f"Failed to save interaction: {e}")
        
        background_tasks.add_task(save_interaction)
        
        return GenerateResponse(
            answer=answer,
            query=request.query,
            context=context,
            session_id=session_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

