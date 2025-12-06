"""
图数据库相关 API（GraphRAG 专用）
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.services.graph_builder import graph_builder
from app.core.neo4j_client import neo4j_client

router = APIRouter()

class CreateNodeRequest(BaseModel):
    name: str
    labels: List[str] = []
    properties: dict = {}

class CreateRelationshipRequest(BaseModel):
    from_entity: str
    to_entity: str
    relation_type: str
    properties: dict = {}

@router.post("/nodes")
async def create_node(request: CreateNodeRequest):
    """创建图节点"""
    try:
        labels_str = ":".join(request.labels) if request.labels else "Entity"
        query = f"""
        MERGE (n:{labels_str} {{name: $name}})
        SET n += $properties
        RETURN n
        """
        results = neo4j_client.execute_query(query, {
            "name": request.name,
            "properties": request.properties
        })
        return {"message": "Node created", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/relationships")
async def create_relationship(request: CreateRelationshipRequest):
    """创建图关系"""
    try:
        success = await graph_builder.create_relationship(
            request.from_entity,
            request.to_entity,
            request.relation_type,
            request.properties
        )
        if success:
            return {"message": "Relationship created successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to create relationship")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/subgraph")
async def get_subgraph(entities: str, depth: int = 2):
    """
    获取实体子图
    
    GraphRAG 核心功能：基于实体查询相关子图
    """
    try:
        from app.services.rag_service import rag_service
        entity_list = [e.strip() for e in entities.split(",")]
        subgraph = await rag_service.graph_subgraph_search(entity_list, depth)
        return subgraph
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_graph_stats():
    """获取图数据库统计信息"""
    try:
        query = """
        MATCH (n)
        RETURN labels(n) as label, count(n) as count
        ORDER BY count DESC
        """
        node_stats = neo4j_client.execute_query(query)
        
        query = """
        MATCH ()-[r]->()
        RETURN type(r) as type, count(r) as count
        ORDER BY count DESC
        """
        rel_stats = neo4j_client.execute_query(query)
        
        return {
            "nodes": node_stats,
            "relationships": rel_stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

