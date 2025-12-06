"""
GraphRAG 检索 API
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from app.services.rag_service import rag_service

router = APIRouter()

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5

class QueryResponse(BaseModel):
    vector_results: List[Dict[str, Any]]
    graph_results: List[Dict[str, Any]]
    query: str

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

