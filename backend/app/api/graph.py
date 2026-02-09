"""图数据库 API"""
import asyncio
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from app.services.graph_builder import graph_builder
from app.core.neo4j_client import neo4j_client
from app.api.auth import get_current_user
from app.models.user import User

router = APIRouter()


def _run_neo4j_sync(query: str, params: dict):
    return neo4j_client.execute_query(query, params)

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
async def create_node(request: CreateNodeRequest, current_user: User = Depends(get_current_user)):
    try:
        labels_str = ":".join(request.labels) if request.labels else "Entity"
        query = f"""
        MERGE (n:{labels_str} {{name: $name}})
        SET n += $properties
        RETURN n
        """
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: neo4j_client.execute_query(query, {
                "name": request.name,
                "properties": request.properties
            }),
        )
        return {"message": "Node created", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/relationships")
async def create_relationship(request: CreateRelationshipRequest, current_user: User = Depends(get_current_user)):
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
    try:
        from app.services.rag_service import rag_service
        entity_list = [e.strip() for e in entities.split(",")]
        subgraph = await rag_service.graph_subgraph_search(entity_list, depth)
        return subgraph
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_graph_stats():
    try:
        loop = asyncio.get_event_loop()
        query_nodes = """
        MATCH (n)
        RETURN labels(n) as label, count(n) as count
        ORDER BY count DESC
        """
        query_rels = """
        MATCH ()-[r]->()
        RETURN type(r) as type, count(r) as count
        ORDER BY count DESC
        """
        node_stats, rel_stats = await asyncio.gather(
            loop.run_in_executor(None, lambda: neo4j_client.execute_query(query_nodes)),
            loop.run_in_executor(None, lambda: neo4j_client.execute_query(query_rels)),
        )
        return {
            "nodes": node_stats,
            "relationships": rel_stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

