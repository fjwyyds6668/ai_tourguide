"""
管理员 API
"""
import os
import uuid
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
from pydantic import BaseModel

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
    上传知识库内容到向量数据库和图数据库
    
    GraphRAG 知识构建：
    1. 存储向量嵌入到 Milvus（用于语义搜索）
    2. 提取实体并构建图结构到 Neo4j（用于关系查询）
    """
    try:
        return await _upload_items_to_graphrag(items, collection_name, build_graph)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

