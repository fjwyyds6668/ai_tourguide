"""
管理员 API
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.interaction import Interaction
from app.services.rag_service import rag_service
from app.services.graph_builder import graph_builder
from app.core.milvus_client import milvus_client
from pydantic import BaseModel

router = APIRouter()

class KnowledgeBaseItem(BaseModel):
    text: str
    text_id: str
    metadata: dict = {}

@router.post("/knowledge/upload")
async def upload_knowledge(
    items: List[KnowledgeBaseItem],
    collection_name: str = "tour_knowledge",
    build_graph: bool = True
):
    """
    上传知识库内容到向量数据库和图数据库
    
    GraphRAG 知识构建：
    1. 存储向量嵌入到 Milvus（用于语义搜索）
    2. 提取实体并构建图结构到 Neo4j（用于关系查询）
    """
    try:
        # 步骤1: 创建集合（如果不存在）
        collection = milvus_client.create_collection_if_not_exists(
            collection_name,
            dimension=384  # 根据使用的模型调整
        )
        
        # 步骤2: 生成嵌入向量并存储到 Milvus
        texts = [item.text for item in items]
        embeddings = [rag_service.generate_embedding(text) for text in texts]
        
        # 准备数据
        entities = [
            [item.text_id for item in items],
            embeddings
        ]
        
        # 插入数据
        collection.insert(entities)
        collection.flush()
        
        # 步骤3: 构建图结构（GraphRAG 核心功能）
        if build_graph:
            for item in items:
                # 提取实体
                entities = rag_service.extract_entities(item.text)
                
                # 存储到图数据库
                await graph_builder.extract_and_store_entities(
                    item.text,
                    item.text_id,
                    entities
                )
        
        return {
            "message": f"Uploaded {len(items)} items successfully",
            "vector_stored": True,
            "graph_built": build_graph,
            "total_entities": sum(len(rag_service.extract_entities(item.text)) for item in items) if build_graph else 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/interactions")
async def get_interaction_analytics(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """获取交互数据分析"""
    interactions = db.query(Interaction).offset(skip).limit(limit).all()
    
    # 统计信息
    total = db.query(Interaction).count()
    by_type = {}
    for interaction in interactions:
        itype = interaction.interaction_type or "unknown"
        by_type[itype] = by_type.get(itype, 0) + 1
    
    return {
        "total": total,
        "by_type": by_type,
        "recent_interactions": interactions
    }

@router.get("/analytics/popular-attractions")
async def get_popular_attractions(db: Session = Depends(get_db)):
    """获取热门景点统计"""
    from sqlalchemy import func
    from app.models.attraction import Attraction
    
    popular = db.query(
        Attraction.id,
        Attraction.name,
        func.count(Interaction.id).label("visit_count")
    ).join(
        Interaction, Attraction.id == Interaction.attraction_id, isouter=True
    ).group_by(Attraction.id, Attraction.name).order_by(
        func.count(Interaction.id).desc()
    ).limit(10).all()
    
    return {"popular_attractions": popular}

