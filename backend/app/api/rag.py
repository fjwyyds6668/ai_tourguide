"""
GraphRAG 检索 API
"""
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.services.rag_service import rag_service
from app.services.session_service import session_service
from app.core.database import get_db
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
    session_id: Optional[str] = None  # 会话ID，用于多轮对话
    character_id: Optional[int] = None  # 角色ID
    use_rag: bool = True  # 是否使用RAG检索增强

class GenerateResponse(BaseModel):
    answer: str
    query: str
    context: str = ""
    session_id: str  # 返回会话ID

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
async def generate_answer(request: GenerateRequest, db: Session = Depends(get_db)):
    """使用硅基流动生成回答（支持RAG增强和多轮对话）"""
    try:
        # 获取或创建会话
        session_id = request.session_id
        if not session_id:
            session_id = session_service.create_session(request.character_id)
        else:
            session = session_service.get_session(session_id)
            if not session:
                session_id = session_service.create_session(request.character_id)
        
        # 获取角色信息（如果有）
        character_prompt = None
        if request.character_id:
            prisma = await get_prisma()
            character = await prisma.character.find_unique(where={"id": request.character_id})
            if character and character.prompt:
                character_prompt = character.prompt
        
        # 获取对话历史
        conversation_history = session_service.get_conversation_history(session_id)
        
        # 如果使用RAG，先获取上下文
        context = ""
        if request.use_rag:
            rag_results = await rag_service.hybrid_search(request.query, top_k=5)
            context = rag_results.get("enhanced_context", "")
        
        # 生成回答
        answer = await rag_service.generate_answer(
            query=request.query,
            context=context,
            use_rag=request.use_rag,
            conversation_history=conversation_history,
            character_prompt=character_prompt
        )
        
        # 保存到会话历史
        session_service.add_message(session_id, "user", request.query)
        session_service.add_message(session_id, "assistant", answer)
        
        # 保存交互记录到数据库
        try:
            interaction = Interaction(
                session_id=session_id,
                character_id=request.character_id,
                query_text=request.query,
                response_text=answer,
                interaction_type="voice_query"
            )
            db.add(interaction)
            db.commit()
        except Exception as e:
            logger.error(f"Failed to save interaction: {e}")
            db.rollback()
        
        return GenerateResponse(
            answer=answer,
            query=request.query,
            context=context,
            session_id=session_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

