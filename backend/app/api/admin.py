"""
管理员 API
"""
import os
import uuid
import logging
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.models.interaction import Interaction
from app.models.user import User
from app.api.auth import get_current_user
from app.services.rag_service import rag_service
from app.services.graph_builder import graph_builder
from app.core.milvus_client import milvus_client
from app.core.prisma_client import get_prisma, disconnect_prisma
from app.core.config import settings
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/uploads/image")
async def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """上传图片附件，返回可访问的 URL（/uploads/images/xxx）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可上传")

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="仅支持上传图片文件")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片大小不能超过 10MB")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in [".png", ".jpg", ".jpeg", ".webp", ".gif"]:
        # 兜底：根据 content_type 猜扩展名
        if file.content_type == "image/png":
            ext = ".png"
        elif file.content_type in ("image/jpg", "image/jpeg"):
            ext = ".jpg"
        elif file.content_type == "image/webp":
            ext = ".webp"
        elif file.content_type == "image/gif":
            ext = ".gif"
        else:
            raise HTTPException(status_code=400, detail="不支持的图片格式")

    # 保存路径：backend/uploads/images
    uploads_root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
    images_dir = os.path.join(uploads_root, "images")
    os.makedirs(images_dir, exist_ok=True)

    filename = f"img_{uuid.uuid4().hex}{ext}"
    abs_path = os.path.join(images_dir, filename)
    with open(abs_path, "wb") as f:
        f.write(content)

    image_url = f"/uploads/images/{filename}"
    return {"message": "上传成功", "image_url": image_url}

class DashboardStatsResponse(BaseModel):
    total_users: int
    attractions_count: int
    interactions_count: int

class KnowledgeBaseItem(BaseModel):
    text: str
    text_id: str
    metadata: dict = {}

class ImportAttractionsRequest(BaseModel):
    """
    从 attractions 表批量导入到 GraphRAG：
    - Milvus: attraction 文本 embedding -> collection
    - Neo4j: Text 节点 + Entity 节点 + MENTIONS 关系
    - 可选：Neo4j Attraction 节点 + NEARBY（同类）关系
    """
    collection_name: str = "tour_knowledge"
    build_graph: bool = True
    build_attraction_graph: bool = True
    active_only: bool = False  # 预留：如后续 attractions 增加 isActive 字段
    limit: Optional[int] = None

def _attraction_to_text(attraction: dict) -> str:
    """将景点记录拼接为用于向量/图谱的文本。"""
    parts = []
    name = attraction.get("name")
    if name:
        parts.append(f"景点：{name}")
    category = attraction.get("category")
    if category:
        parts.append(f"类别：{category}")
    location = attraction.get("location")
    if location:
        parts.append(f"位置：{location}")
    desc = attraction.get("description")
    if desc:
        parts.append(f"介绍：{desc}")
    # 坐标可选，避免噪声过大
    lat = attraction.get("latitude")
    lng = attraction.get("longitude")
    if lat is not None and lng is not None:
        parts.append(f"坐标：({lat}, {lng})")
    return "\n".join(parts).strip()

async def _sync_attraction_to_graphrag(attraction_dict: dict, operation: str = "upsert"):
    """
    同步单个景点到 GraphRAG（Milvus + Neo4j）
    
    Args:
        attraction_dict: 景点字典，包含 id, name, description 等字段
        operation: "upsert"（创建/更新）或 "delete"（删除）
    """
    if not settings.AUTO_UPDATE_GRAPH_RAG:
        logger.debug("GraphRAG 自动更新已禁用，跳过同步")
        return
    
    try:
        text_id = f"attraction_{attraction_dict.get('id')}"
        collection_name = settings.GRAPHRAG_COLLECTION_NAME
        
        if operation == "delete":
            # 删除操作：从 Milvus 和 Neo4j 中移除
            try:
                # 从 Milvus 删除
                from pymilvus import utility
                if utility.has_collection(collection_name):
                    collection = milvus_client.get_collection(collection_name)
                    # Milvus 需要通过表达式删除，使用 text_id 字段
                    expr = f'text_id == "{text_id}"'
                    collection.delete(expr)
                    collection.flush()
                    logger.info(f"已从 Milvus 删除景点: {text_id}")
            except Exception as e:
                logger.warning(f"从 Milvus 删除失败: {e}")
            
            try:
                # 从 Neo4j 删除 Text 节点和相关关系
                query = """
                MATCH (t:Text {id: $text_id})
                DETACH DELETE t
                """
                graph_builder.client.execute_query(query, {"text_id": text_id})
                logger.info(f"已从 Neo4j 删除文本节点: {text_id}")
            except Exception as e:
                logger.warning(f"从 Neo4j 删除失败: {e}")
            
            # 删除 Attraction 节点（如果存在）
            try:
                query = """
                MATCH (a:Attraction {id: $id})
                DETACH DELETE a
                """
                graph_builder.client.execute_query(query, {"id": attraction_dict.get('id')})
                logger.info(f"已从 Neo4j 删除景点节点: {attraction_dict.get('id')}")
            except Exception as e:
                logger.warning(f"从 Neo4j 删除景点节点失败: {e}")
        
        else:
            # 创建/更新操作
            text = _attraction_to_text(attraction_dict)
            if not text:
                logger.warning(f"景点 {attraction_dict.get('id')} 文本为空，跳过 GraphRAG 同步")
                return
            
            # 1. 更新 Milvus（先删除旧的，再插入新的）
            try:
                collection = milvus_client.create_collection_if_not_exists(
                    collection_name,
                    dimension=384
                )
                
                # 删除旧数据（如果存在）
                from pymilvus import utility
                if utility.has_collection(collection_name):
                    expr = f'text_id == "{text_id}"'
                    collection.delete(expr)
                    collection.flush()
                
                # 生成新的嵌入向量并插入
                embedding = rag_service.generate_embedding(text)
                entities = [
                    [text_id],
                    [embedding]
                ]
                collection.insert(entities)
                collection.flush()
                logger.info(f"已更新 Milvus 中的景点: {text_id}")
            except Exception as e:
                logger.error(f"更新 Milvus 失败: {e}")
                raise
            
            # 2. 更新 Neo4j（创建/更新 Text 节点和实体）
            try:
                # 删除旧的 Text 节点和相关关系
                query = """
                MATCH (t:Text {id: $text_id})
                DETACH DELETE t
                """
                graph_builder.client.execute_query(query, {"text_id": text_id})
                
                # 提取实体并创建新的图结构
                extracted = rag_service.extract_entities(text)
                await graph_builder.extract_and_store_entities(text, text_id, extracted)
                logger.info(f"已更新 Neo4j 中的景点: {text_id}, 提取了 {len(extracted)} 个实体")
            except Exception as e:
                logger.error(f"更新 Neo4j 失败: {e}")
                raise
            
            # 3. 创建/更新 Attraction 节点（用于景点图谱）
            try:
                await graph_builder.create_attraction_node(attraction_dict)
                logger.info(f"已更新 Neo4j 中的景点节点: {attraction_dict.get('name')}")
            except Exception as e:
                logger.warning(f"更新景点节点失败: {e}")
                # 不抛出异常，因为这不是关键操作
        
    except Exception as e:
        logger.error(f"同步景点到 GraphRAG 失败: {e}", exc_info=True)
        # 不抛出异常，避免影响主流程

def _serialize_metadata(metadata: dict) -> str:
    """将 metadata dict 序列化为 JSON 字符串"""
    return json.dumps(metadata or {}, ensure_ascii=False)


def _deserialize_metadata(metadata_str: str | None) -> dict:
    """将 metadata JSON 字符串反序列化为 dict"""
    if not metadata_str:
        return {}
    try:
        return json.loads(metadata_str)
    except Exception:
        return {}


async def _delete_knowledge_from_milvus(text_id: str, collection_name: str = "tour_knowledge") -> None:
    """从 Milvus 删除指定 text_id 的向量"""
    try:
        from pymilvus import utility
        if utility.has_collection(collection_name):
            collection = milvus_client.get_collection(collection_name)
            expr = f'text_id == "{text_id}"'
            collection.delete(expr)
            collection.flush()
            logger.info(f"已从 Milvus 删除知识库: {text_id}")
    except Exception as e:
        logger.warning(f"从 Milvus 删除失败: {e}")


async def _delete_knowledge_from_neo4j(text_id: str) -> None:
    """从 Neo4j 删除指定 text_id 的 Text 节点及其关联的景区簇（如果该景区不再被其他 Text 描述）"""
    try:
        # 1) 删除 Text 节点本身
        query_text = """
        MATCH (t:Text {id: $text_id})
        DETACH DELETE t
        """
        graph_builder.client.execute_query(query_text, {"text_id": text_id})

        # 2) 删除由该 Text 衍生出的景区簇（仅当该景区不再被其他 Text 描述时）
        query_cluster = """
        MATCH (s:ScenicSpot)<-[:DESCRIBES]-(:Text {id: $text_id})
        WITH s
        OPTIONAL MATCH (s)<-[:DESCRIBES]-(other:Text)
        WITH s, collect(other.id) AS others
        WHERE size(others) = 0 OR (size(others) = 1 AND others[0] IS NULL)
        OPTIONAL MATCH (s)-[r]-(n)
        DETACH DELETE s, n
        """
        graph_builder.client.execute_query(query_cluster, {"text_id": text_id})
        logger.info(f"已从 Neo4j 删除知识库及景区簇（如适用）: {text_id}")
    except Exception as e:
        logger.warning(f"从 Neo4j 删除失败: {e}")


async def _upload_items_to_graphrag(items: List[KnowledgeBaseItem], collection_name: str, build_graph: bool) -> dict:
    """复用 /admin/knowledge/upload 的逻辑，供批量导入调用。"""
    # 步骤1: 创建集合（如果不存在）
    collection = milvus_client.create_collection_if_not_exists(
        collection_name,
        dimension=384
    )

    # 步骤2: 生成嵌入向量并存储到 Milvus
    texts = [item.text for item in items]
    embeddings = [rag_service.generate_embedding(text) for text in texts]

    # 准备数据（与 milvus schema: [text_id, embedding]）
    entities = [
        [item.text_id for item in items],
        embeddings
    ]

    collection.insert(entities)
    collection.flush()

    # 步骤3: 构建图结构
    total_entities = 0
    if build_graph:
        for item in items:
            # 优先尝试解析为景区结构化信息
            parsed = None
            try:
                parsed = await rag_service.parse_scenic_text(item.text)
            except Exception as e:
                logger.debug(f"parse_scenic_text failed for text_id={item.text_id}: {e}")
            
            if parsed:
                # 景区类文本：只构建景区簇，不创建通用实体散点
                await graph_builder.build_scenic_cluster(parsed, text_id=item.text_id)
                logger.info(f"Built scenic cluster for text_id={item.text_id}, scenic_spot={parsed.get('scenic_spot')}")
                # 统计：景区簇里的节点数（位置+子景点+特色+荣誉）
                total_entities += (
                    len(parsed.get("location", [])) +
                    len(parsed.get("spots", [])) +
                    len(parsed.get("features", [])) +
                    len(parsed.get("awards", [])) +
                    1  # 景区节点本身
                )
            else:
                # 非景区类文本：走通用实体抽取路径
                extracted = rag_service.extract_entities(item.text)
                total_entities += len(extracted)
                await graph_builder.extract_and_store_entities(item.text, item.text_id, extracted)

    return {
        "message": f"Uploaded {len(items)} items successfully",
        "vector_stored": True,
        "graph_built": build_graph,
        "total_entities": total_entities
    }

@router.post("/knowledge/upload")
async def upload_knowledge(
    items: List[KnowledgeBaseItem],
    collection_name: str = "tour_knowledge",
    build_graph: bool = True
):
    """
    上传知识库内容到向量数据库和图数据库（自动同步到 GraphRAG），并持久化到 PostgreSQL
    """
    try:
        # 先同步到 GraphRAG（Milvus + Neo4j）
        result = await _upload_items_to_graphrag(items, collection_name, build_graph)

        # 再持久化到 PostgreSQL（Prisma）
        prisma = await get_prisma()
        for item in items:
            if not item.text_id:
                continue
            try:
                meta_str = _serialize_metadata(item.metadata)
                await prisma.knowledge.upsert(
                    where={"textId": item.text_id},
                    data={
                        "create": {
                            "textId": item.text_id,
                            "text": item.text,
                            "metadata": meta_str,
                        },
                        "update": {
                            "text": item.text,
                            "metadata": meta_str,
                        },
                    },
                )
            except Exception as e:
                logger.error(f"持久化知识 {item.text_id} 失败: {e}")

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge", response_model=List[KnowledgeBaseItem])
async def list_knowledge():
    """
    获取知识库列表（管理端使用，来自 PostgreSQL 的 knowledge 表）
    """
    prisma = await get_prisma()
    rows = await prisma.knowledge.find_many(order={"id": "asc"}, take=1000)
    return [
        KnowledgeBaseItem(
            text_id=row.textId,
            text=row.text,
            metadata=_deserialize_metadata(row.metadata),
        )
        for row in rows
    ]

@router.put("/knowledge/{text_id}")
async def update_knowledge(
    text_id: str,
    item: KnowledgeBaseItem,
    collection_name: str = "tour_knowledge",
    build_graph: bool = True
):
    """更新知识库内容（自动同步到 GraphRAG）"""
    if not settings.AUTO_UPDATE_GRAPH_RAG:
        raise HTTPException(status_code=400, detail="GraphRAG 自动更新已禁用")
    
    try:
        # 确保 text_id 一致
        item.text_id = text_id
        
        # 先删除旧数据（复用公共函数）
        await _delete_knowledge_from_milvus(text_id, collection_name)
        await _delete_knowledge_from_neo4j(text_id)
        
        # 重新上传（使用现有的上传逻辑）
        result = await _upload_items_to_graphrag([item], collection_name, build_graph)

        # 更新 PostgreSQL 中的记录
        prisma = await get_prisma()
        try:
            await prisma.knowledge.update(
                where={"textId": text_id},
                data={
                    "text": item.text,
                    "metadata": _serialize_metadata(item.metadata),
                },
            )
        except Exception as e:
            logger.error(f"更新知识 {text_id}（PostgreSQL）失败: {e}")

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/knowledge/{text_id}")
async def delete_knowledge(
    text_id: str,
    collection_name: str = "tour_knowledge"
):
    """删除知识库内容（自动从 GraphRAG 删除）"""
    if not settings.AUTO_UPDATE_GRAPH_RAG:
        raise HTTPException(status_code=400, detail="GraphRAG 自动更新已禁用")
    
    try:
        # 从 Milvus 和 Neo4j 删除（复用公共函数）
        await _delete_knowledge_from_milvus(text_id, collection_name)
        await _delete_knowledge_from_neo4j(text_id)
        
        # 从 PostgreSQL 删除
        try:
            prisma = await get_prisma()
            await prisma.knowledge.delete(where={"textId": text_id})
        except Exception as e:
            logger.error(f"从 PostgreSQL 删除知识 {text_id} 失败: {e}")
        
        return {"message": f"Knowledge item {text_id} deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/knowledge/{text_id}/rebuild-cluster")
async def rebuild_knowledge_cluster(
    text_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    重建某个知识条目的图簇（先删除旧簇，再根据当前文本重新构建）
    用于修复"节点没有聚成一簇"的问题
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    
    try:
        # 1. 从 PostgreSQL 获取知识内容
        prisma = await get_prisma()
        knowledge = await prisma.knowledge.find_unique(where={"textId": text_id})
        if not knowledge:
            raise HTTPException(status_code=404, detail=f"知识 {text_id} 不存在")
        
        # 2. 先删除旧簇（复用公共函数）
        await _delete_knowledge_from_neo4j(text_id)
        
        # 3. 重新构建簇
        item = KnowledgeBaseItem(
            text_id=text_id,
            text=knowledge.text,
            metadata=_deserialize_metadata(knowledge.metadata)
        )
        
        # 重新上传（会触发 parse_scenic_text + build_scenic_cluster）
        result = await _upload_items_to_graphrag([item], "tour_knowledge", build_graph=True)
        
        return {
            "message": f"已重建知识 {text_id} 的图簇",
            "result": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重建簇失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"重建簇失败: {str(e)}")


@router.post("/knowledge/clear-graph")
async def clear_graph_database(
    current_user: User = Depends(get_current_user),
):
    """
    清空整个 Neo4j 图数据库（危险操作，仅管理员）
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    
    try:
        query = "MATCH (n) DETACH DELETE n"
        graph_builder.client.execute_query(query)
        return {"message": "已清空图数据库"}
    except Exception as e:
        logger.error(f"清空图数据库失败: {e}")
        raise HTTPException(status_code=500, detail=f"清空失败: {str(e)}")


@router.post("/knowledge/clear-vector")
async def clear_vector_database(
    collection_name: str = "tour_knowledge",
    current_user: User = Depends(get_current_user),
):
    """
    清空 Milvus 向量数据库的指定 collection（危险操作，仅管理员）
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    
    try:
        from pymilvus import utility
        
        if not milvus_client.connected:
            milvus_client.connect()
        
        if utility.has_collection(collection_name):
            # 删除整个 collection（最彻底）
            utility.drop_collection(collection_name)
            logger.info(f"已删除 Milvus collection: {collection_name}")
            return {"message": f"已清空向量数据库（collection: {collection_name}）"}
        else:
            return {"message": f"Collection {collection_name} 不存在，无需清空"}
    except Exception as e:
        logger.error(f"清空向量数据库失败: {e}")
        raise HTTPException(status_code=500, detail=f"清空失败: {str(e)}")

@router.post("/knowledge/import_attractions")
async def import_attractions_to_graphrag(req: ImportAttractionsRequest):
    """
    从 PostgreSQL 的 attractions 表批量导入到：
    - Milvus（向量库）
    - Neo4j（图数据库：Text/Entity/MENTIONS）
    - 可选：Neo4j（Attraction 节点与 NEARBY 关系）
    """
    prisma = None
    try:
        prisma = await get_prisma()

        # Prisma 返回的是对象，这里统一转 dict（通过 __dict__ 不稳定，手动映射）
        attractions = await prisma.attraction.find_many(
            order={"id": "asc"},
            take=req.limit
        )

        att_dicts = []
        for a in attractions:
            att_dicts.append({
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "location": a.location,
                "latitude": a.latitude,
                "longitude": a.longitude,
                "category": a.category,
            })

        # 1) 可选：构建 Attraction 图谱（节点+同类 NEARBY）
        if req.build_attraction_graph:
            await graph_builder.build_attraction_graph(att_dicts)

        # 2) 写入 GraphRAG（向量 + Text/Entity/MENTIONS）
        items: List[KnowledgeBaseItem] = []
        for att in att_dicts:
            text_id = f"attraction_{att['id']}"
            text = _attraction_to_text(att)
            if not text:
                continue
            items.append(KnowledgeBaseItem(text=text, text_id=text_id, metadata={"source": "attractions"}))

        result = await _upload_items_to_graphrag(items, req.collection_name, req.build_graph)
        result.update({
            "imported_attractions": len(items),
            "build_attraction_graph": req.build_attraction_graph
        })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 避免脚本/一次性任务场景下连接泄露
        try:
            await disconnect_prisma()
        except Exception:
            pass

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

@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(db: Session = Depends(get_db)):
    """仪表盘统计（来自真实数据库）"""
    try:
        from app.models.attraction import Attraction

        total_users = db.query(User).count()
        attractions_count = db.query(Attraction).count()
        interactions_count = db.query(Interaction).count()

        return DashboardStatsResponse(
            total_users=total_users,
            attractions_count=attractions_count,
            interactions_count=interactions_count,
        )
    except Exception as e:
        import traceback
        error_detail = f"获取统计信息失败: {str(e)}"
        print(f"Error in get_dashboard_stats: {error_detail}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_detail)


@router.post("/profile/avatar")
async def upload_admin_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """管理员上传头像（保存到本地并写入 users.avatar_url）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可上传头像")

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="仅支持上传图片文件")

    # 限制文件大小（5MB）
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片大小不能超过 5MB")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in [".png", ".jpg", ".jpeg", ".webp", ".gif"]:
        # 兜底：根据 content_type 猜扩展名
        if file.content_type == "image/png":
            ext = ".png"
        elif file.content_type in ("image/jpg", "image/jpeg"):
            ext = ".jpg"
        elif file.content_type == "image/webp":
            ext = ".webp"
        elif file.content_type == "image/gif":
            ext = ".gif"
        else:
            raise HTTPException(status_code=400, detail="不支持的图片格式")

    # 保存路径：backend/uploads/avatars
    uploads_root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
    avatars_dir = os.path.join(uploads_root, "avatars")
    os.makedirs(avatars_dir, exist_ok=True)

    filename = f"{current_user.id}_{uuid.uuid4().hex}{ext}"
    abs_path = os.path.join(avatars_dir, filename)
    with open(abs_path, "wb") as f:
        f.write(content)

    # 可访问 URL：/uploads/avatars/xxx
    avatar_url = f"/uploads/avatars/{filename}"
    current_user.avatar_url = avatar_url
    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    return {
        "message": "头像上传成功",
        "avatar_url": avatar_url,
        "user": {
            "id": current_user.id,
            "username": current_user.username,
            "email": current_user.email,
            "is_admin": current_user.is_admin,
            "avatar_url": current_user.avatar_url,
        },
    }

class TTSConfigResponse(BaseModel):
    """TTS配置响应"""
    xfyun_voice: str
    local_tts_enabled: bool
    local_tts_force: bool
    local_tts_engine: str
    cosyvoice2_model_path: str
    cosyvoice2_device: str
    cosyvoice2_language: str

class TTSConfigUpdateRequest(BaseModel):
    """TTS配置更新请求"""
    xfyun_voice: Optional[str] = None
    local_tts_enabled: Optional[bool] = None
    local_tts_force: Optional[bool] = None
    local_tts_engine: Optional[str] = None
    cosyvoice2_model_path: Optional[str] = None
    cosyvoice2_device: Optional[str] = None
    cosyvoice2_language: Optional[str] = None

def _get_env_file_path():
    """获取 .env 文件路径"""
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(backend_dir, ".env")

@router.get("/settings/tts", response_model=TTSConfigResponse)
async def get_tts_config(
    current_user: User = Depends(get_current_user),
):
    """获取TTS配置（仅管理员，从.env文件实时读取）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可查看配置")
    
    env_file = _get_env_file_path()
    
    xfyun_voice = settings.XFYUN_VOICE
    local_tts_enabled = settings.LOCAL_TTS_ENABLED
    local_tts_force = settings.LOCAL_TTS_FORCE
    local_tts_engine = settings.LOCAL_TTS_ENGINE
    cosyvoice2_model_path = settings.COSYVOICE2_MODEL_PATH
    cosyvoice2_device = settings.COSYVOICE2_DEVICE
    cosyvoice2_language = settings.COSYVOICE2_LANGUAGE
    
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("LOCAL_TTS_ENABLED="):
                    value = line.split("=", 1)[1].strip()
                    local_tts_enabled = value.lower() in ("true", "1", "yes")
                elif line.startswith("XFYUN_VOICE="):
                    value = line.split("=", 1)[1].strip()
                    if value:
                        xfyun_voice = value
                elif line.startswith("LOCAL_TTS_FORCE="):
                    value = line.split("=", 1)[1].strip()
                    local_tts_force = value.lower() in ("true", "1", "yes")
                elif line.startswith("LOCAL_TTS_ENGINE="):
                    value = line.split("=", 1)[1].strip()
                    if value:
                        local_tts_engine = value
                elif line.startswith("COSYVOICE2_MODEL_PATH="):
                    value = line.split("=", 1)[1].strip()
                    if value:
                        cosyvoice2_model_path = value
                elif line.startswith("COSYVOICE2_DEVICE="):
                    value = line.split("=", 1)[1].strip()
                    if value:
                        cosyvoice2_device = value
                elif line.startswith("COSYVOICE2_LANGUAGE="):
                    value = line.split("=", 1)[1].strip()
                    if value:
                        cosyvoice2_language = value
    
    return TTSConfigResponse(
        xfyun_voice=xfyun_voice,
        local_tts_enabled=local_tts_enabled,
        local_tts_force=local_tts_force,
        local_tts_engine=local_tts_engine,
        cosyvoice2_model_path=cosyvoice2_model_path,
        cosyvoice2_device=cosyvoice2_device,
        cosyvoice2_language=cosyvoice2_language,
    )

@router.put("/settings/tts")
async def update_tts_config(
    req: TTSConfigUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    """更新TTS配置（仅管理员，需要重启服务才能生效）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可修改配置")
    
    env_file = _get_env_file_path()
    
    if not os.path.exists(env_file):
        with open(env_file, "w", encoding="utf-8") as f:
            f.write("# TTS Configuration\n")
    
    env_lines = []
    with open(env_file, "r", encoding="utf-8") as f:
        env_lines = f.readlines()
    
    # 更新或添加配置项
    updated_keys = set()
    new_lines = []
    
    for line in env_lines:
        stripped = line.strip()
        # 跳过空行和注释（但保留它们）
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        
        # 检查是否是我们要更新的配置项
        if stripped.startswith("XFYUN_VOICE="):
            if req.xfyun_voice is not None:
                new_lines.append(f"XFYUN_VOICE={req.xfyun_voice}\n")
                updated_keys.add("XFYUN_VOICE")
            else:
                new_lines.append(line)
        elif stripped.startswith("LOCAL_TTS_ENABLED="):
            if req.local_tts_enabled is not None:
                new_lines.append(f"LOCAL_TTS_ENABLED={str(req.local_tts_enabled).lower()}\n")
                updated_keys.add("LOCAL_TTS_ENABLED")
            else:
                new_lines.append(line)
        elif stripped.startswith("LOCAL_TTS_FORCE="):
            if req.local_tts_force is not None:
                new_lines.append(f"LOCAL_TTS_FORCE={str(req.local_tts_force).lower()}\n")
                updated_keys.add("LOCAL_TTS_FORCE")
            else:
                new_lines.append(line)
        elif stripped.startswith("LOCAL_TTS_ENGINE="):
            if req.local_tts_engine is not None:
                new_lines.append(f"LOCAL_TTS_ENGINE={req.local_tts_engine}\n")
                updated_keys.add("LOCAL_TTS_ENGINE")
            else:
                new_lines.append(line)
        elif stripped.startswith("COSYVOICE2_MODEL_PATH="):
            if req.cosyvoice2_model_path is not None:
                new_lines.append(f"COSYVOICE2_MODEL_PATH={req.cosyvoice2_model_path}\n")
                updated_keys.add("COSYVOICE2_MODEL_PATH")
            else:
                new_lines.append(line)
        elif stripped.startswith("COSYVOICE2_DEVICE="):
            if req.cosyvoice2_device is not None:
                new_lines.append(f"COSYVOICE2_DEVICE={req.cosyvoice2_device}\n")
                updated_keys.add("COSYVOICE2_DEVICE")
            else:
                new_lines.append(line)
        elif stripped.startswith("COSYVOICE2_LANGUAGE="):
            if req.cosyvoice2_language is not None:
                new_lines.append(f"COSYVOICE2_LANGUAGE={req.cosyvoice2_language}\n")
                updated_keys.add("COSYVOICE2_LANGUAGE")
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    
    # 添加未存在的配置项
    if req.xfyun_voice is not None and "XFYUN_VOICE" not in updated_keys:
        new_lines.append(f"XFYUN_VOICE={req.xfyun_voice}\n")
    if req.local_tts_enabled is not None and "LOCAL_TTS_ENABLED" not in updated_keys:
        new_lines.append(f"LOCAL_TTS_ENABLED={str(req.local_tts_enabled).lower()}\n")
    if req.local_tts_force is not None and "LOCAL_TTS_FORCE" not in updated_keys:
        new_lines.append(f"LOCAL_TTS_FORCE={str(req.local_tts_force).lower()}\n")
    if req.local_tts_engine is not None and "LOCAL_TTS_ENGINE" not in updated_keys:
        new_lines.append(f"LOCAL_TTS_ENGINE={req.local_tts_engine}\n")
    if req.cosyvoice2_model_path is not None and "COSYVOICE2_MODEL_PATH" not in updated_keys:
        new_lines.append(f"COSYVOICE2_MODEL_PATH={req.cosyvoice2_model_path}\n")
    if req.cosyvoice2_device is not None and "COSYVOICE2_DEVICE" not in updated_keys:
        new_lines.append(f"COSYVOICE2_DEVICE={req.cosyvoice2_device}\n")
    if req.cosyvoice2_language is not None and "COSYVOICE2_LANGUAGE" not in updated_keys:
        new_lines.append(f"COSYVOICE2_LANGUAGE={req.cosyvoice2_language}\n")
    
    # 写回 .env 文件
    try:
        with open(env_file, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入配置文件失败: {str(e)}")
    
    return {
        "message": "配置已更新（需要重启后端服务才能生效）",
        "updated": {
            "xfyun_voice": req.xfyun_voice if req.xfyun_voice is not None else settings.XFYUN_VOICE,
            "local_tts_enabled": req.local_tts_enabled if req.local_tts_enabled is not None else settings.LOCAL_TTS_ENABLED,
            "local_tts_force": req.local_tts_force if req.local_tts_force is not None else settings.LOCAL_TTS_FORCE,
            "local_tts_engine": req.local_tts_engine if req.local_tts_engine is not None else settings.LOCAL_TTS_ENGINE,
            "cosyvoice2_model_path": req.cosyvoice2_model_path if req.cosyvoice2_model_path is not None else settings.COSYVOICE2_MODEL_PATH,
            "cosyvoice2_device": req.cosyvoice2_device if req.cosyvoice2_device is not None else settings.COSYVOICE2_DEVICE,
            "cosyvoice2_language": req.cosyvoice2_language if req.cosyvoice2_language is not None else settings.COSYVOICE2_LANGUAGE,
        }
    }

