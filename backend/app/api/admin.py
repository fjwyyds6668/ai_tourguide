"""
管理员 API
"""
import os
import uuid
import logging
import json
import asyncio
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
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_prisma_model(prisma, *candidate_names: str):
    """
    prisma-client-py 对 model 的访问名在不同版本/配置下可能是：
    - scenicspot
    - scenicSpot
    这里做一层兼容，避免因生成代码差异导致运行期报错。
    """
    for name in candidate_names:
        if hasattr(prisma, name):
            return getattr(prisma, name)
    raise AttributeError(f"Prisma model not found among candidates: {candidate_names}")


class ScenicSpotCreateRequest(BaseModel):
    name: str
    location: Optional[str] = None
    description: Optional[str] = None
    cover_image_url: Optional[str] = None


class ScenicSpotUpdateRequest(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    cover_image_url: Optional[str] = None


class ScenicSpotResponse(BaseModel):
    id: int
    name: str
    location: Optional[str] = None
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    attractions_count: int = 0
    knowledge_count: int = 0

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
    scenic_spot_id: Optional[int] = None


class AttractionAdminCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    audio_url: Optional[str] = None


class AttractionAdminUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    audio_url: Optional[str] = None


@router.post("/scenic-spots/reclassify")
async def reclassify_existing_data(
    current_user: User = Depends(get_current_user),
    limit: int = 500,
):
    """
    批量归类/修复：对历史数据按规则/LLM 归类到景区（仅管理员）
    - Knowledge：优先 parse_scenic_text 识别 scenic_spot
    - Attraction：优先 parse_attraction_text + location/字段启发式
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")

    prisma = await get_prisma()
    scenic_model = _get_prisma_model(prisma, "scenicspot", "scenicSpot")

    updated_knowledge = 0
    updated_attractions = 0

    # 1) Knowledge 归类（只处理 scenicSpotId 为空的）
    know_rows = await prisma.knowledge.find_many(
        where={"scenicSpotId": None},
        take=limit,
        order={"id": "asc"},
    )
    for k in know_rows:
        try:
            parsed = await rag_service.parse_scenic_text(k.text)
            if not parsed or not parsed.get("scenic_spot"):
                continue
            scenic_name = str(parsed.get("scenic_spot")).strip()
            scenic = await scenic_model.upsert(
                where={"name": scenic_name},
                data={
                    "create": {"name": scenic_name, "location": "、".join(parsed.get("location") or []) or None},
                    "update": {"location": "、".join(parsed.get("location") or []) or None},
                },
            )
            await prisma.knowledge.update(where={"textId": k.textId}, data={"scenicSpotId": scenic.id})
            updated_knowledge += 1
        except Exception:
            continue

    # 2) Attraction 归类（只处理 scenicSpotId 为空的）
    att_rows = await prisma.attraction.find_many(
        where={"scenicSpotId": None},
        take=limit,
        order={"id": "asc"},
    )
    for a in att_rows:
        try:
            text = _attraction_to_text(
                {
                    "name": a.name,
                    "category": a.category,
                    "location": a.location,
                    "description": a.description,
                    "latitude": a.latitude,
                    "longitude": a.longitude,
                }
            )
            parsed = await rag_service.parse_attraction_text(a.name, text)

            locations = []
            if parsed and isinstance(parsed.get("location"), list):
                locations = [str(x).strip() for x in parsed.get("location") if str(x).strip()]

            # 粗归类策略：先用 attraction.location 的“最后一级行政区”，没有就跳过
            scenic_guess = None
            if locations:
                scenic_guess = locations[-1]
            if not scenic_guess:
                continue

            scenic = await scenic_model.upsert(
                where={"name": scenic_guess},
                data={
                    "create": {"name": scenic_guess, "location": "、".join(locations) or None},
                    "update": {"location": "、".join(locations) or None},
                },
            )
            await prisma.attraction.update(where={"id": a.id}, data={"scenicSpotId": scenic.id})
            updated_attractions += 1
        except Exception:
            continue

    return {
        "updated_knowledge": updated_knowledge,
        "updated_attractions": updated_attractions,
        "limit": limit,
    }

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


def _normalize_scenic_name(name: str) -> str:
    """与 graph_builder.build_scenic_cluster 里一致的景区名归一化（仅用于迁移/兼容旧数据）。"""
    name = str(name or "").strip()
    for suffix in ["旅游度假区", "旅游区", "度假区", "风景区", "景区"]:
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[:-len(suffix)]
            break
    return name.strip()


@router.get("/scenic-spots", response_model=List[ScenicSpotResponse])
async def list_scenic_spots(
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 200,
):
    """景区列表（含景点数/知识数统计，仅管理员）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")

    prisma = await get_prisma()
    scenic_model = _get_prisma_model(prisma, "scenicspot", "scenicSpot")

    # 限制最大分页，避免一次性拉太多
    limit = max(1, min(int(limit), 1000))
    skip = max(0, int(skip))

    rows = await scenic_model.find_many(order={"id": "asc"}, skip=skip, take=limit)
    if not rows:
        return []

    scenic_ids = [int(s.id) for s in rows]

    # 简单可靠：逐个景区 count，避免与底层表名/大小写相关的 query_raw 兼容问题
    counts_map: dict[int, dict] = {}
    for sid in scenic_ids:
        try:
            a_cnt = await prisma.attraction.count(where={"scenicSpotId": sid})
        except Exception:
            a_cnt = 0
        try:
            k_cnt = await prisma.knowledge.count(where={"scenicSpotId": sid})
        except Exception:
            k_cnt = 0
        counts_map[sid] = {"attractions_count": a_cnt, "knowledge_count": k_cnt}

    res: List[ScenicSpotResponse] = []
    for s in rows:
        c = counts_map.get(int(s.id), {"attractions_count": 0, "knowledge_count": 0})
        res.append(
            ScenicSpotResponse(
                id=s.id,
                name=s.name,
                location=getattr(s, "location", None),
                description=getattr(s, "description", None),
                cover_image_url=getattr(s, "coverImageUrl", None) or getattr(s, "cover_image_url", None),
                attractions_count=int(c.get("attractions_count") or 0),
                knowledge_count=int(c.get("knowledge_count") or 0),
            )
        )
    return res


@router.post("/scenic-spots", response_model=ScenicSpotResponse)
async def create_scenic_spot(req: ScenicSpotCreateRequest, current_user: User = Depends(get_current_user)):
    """创建景区（仅管理员）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")

    prisma = await get_prisma()
    scenic_model = _get_prisma_model(prisma, "scenicspot", "scenicSpot")

    created = await scenic_model.create(
        data={
            "name": req.name,
            "location": req.location,
            "description": req.description,
            "coverImageUrl": req.cover_image_url,
        }
    )
    return ScenicSpotResponse(
        id=created.id,
        name=created.name,
        location=getattr(created, "location", None),
        description=getattr(created, "description", None),
        cover_image_url=getattr(created, "coverImageUrl", None) or getattr(created, "cover_image_url", None),
        attractions_count=0,
        knowledge_count=0,
    )


@router.put("/scenic-spots/{scenic_spot_id}", response_model=ScenicSpotResponse)
async def update_scenic_spot(
    scenic_spot_id: int,
    req: ScenicSpotUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    """更新景区（仅管理员）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")

    prisma = await get_prisma()
    scenic_model = _get_prisma_model(prisma, "scenicspot", "scenicSpot")

    data = {}
    if req.name is not None:
        data["name"] = req.name
    if req.location is not None:
        data["location"] = req.location
    if req.description is not None:
        data["description"] = req.description
    if req.cover_image_url is not None:
        data["coverImageUrl"] = req.cover_image_url

    updated = await scenic_model.update(where={"id": scenic_spot_id}, data=data)

    attractions_count = await prisma.attraction.count(where={"scenicSpotId": scenic_spot_id})
    knowledge_count = await prisma.knowledge.count(where={"scenicSpotId": scenic_spot_id})
    return ScenicSpotResponse(
        id=updated.id,
        name=updated.name,
        location=getattr(updated, "location", None),
        description=getattr(updated, "description", None),
        cover_image_url=getattr(updated, "coverImageUrl", None) or getattr(updated, "cover_image_url", None),
        attractions_count=attractions_count,
        knowledge_count=knowledge_count,
    )


@router.delete("/scenic-spots/{scenic_spot_id}")
async def delete_scenic_spot(
    scenic_spot_id: int,
    cascade: bool = False,
    current_user: User = Depends(get_current_user),
):
    """
    删除景区（仅管理员）
    - 默认：若景区下仍有景点/知识，阻止删除
    - cascade=true：级联删除该景区下所有知识与景点（含 Neo4j/Milvus 清理），再删除景区
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")

    prisma = await get_prisma()
    scenic_model = _get_prisma_model(prisma, "scenicspot", "scenicSpot")

    # 分批拉取，避免 take=100000 占用内存
    async def _fetch_all(model, where: dict, batch: int = 500):
        out = []
        skip = 0
        while True:
            rows = await model.find_many(where=where, order={"id": "asc"}, skip=skip, take=batch)
            if not rows:
                break
            out.extend(rows)
            skip += len(rows)
        return out

    attractions = await _fetch_all(prisma.attraction, {"scenicSpotId": scenic_spot_id}, batch=500)
    knowledge = await _fetch_all(prisma.knowledge, {"scenicSpotId": scenic_spot_id}, batch=500)

    if (attractions or knowledge) and not cascade:
        raise HTTPException(status_code=400, detail="该景区下仍有关联的景点/知识，请先清空或使用 cascade=true 级联删除")

    if cascade:
        # 级联删除（批处理优先）：Milvus + Neo4j 清理尽量批量；PG 优先 delete_many
        collection_name = settings.GRAPHRAG_COLLECTION_NAME or "tour_knowledge"

        attraction_ids = [int(a.id) for a in attractions]
        attraction_text_ids = [f"attraction_{aid}" for aid in attraction_ids]
        knowledge_text_ids = [str(k.textId) for k in knowledge if getattr(k, "textId", None)]

        # 1) Milvus 批量删除（景点 + 知识）
        try:
            await _delete_text_ids_from_milvus(attraction_text_ids + knowledge_text_ids, collection_name=collection_name)
        except Exception as e:
            logger.warning(f"Milvus batch delete failed: {e}")

        # 2) Neo4j 批量删除
        # 2.1) 删除景点 Text 节点（attraction_{id}）
        if attraction_text_ids:
            try:
                q_del_texts = """
                UNWIND $ids AS tid
                MATCH (t:Text {id: tid})
                DETACH DELETE t
                """
                graph_builder.client.execute_query(q_del_texts, {"ids": attraction_text_ids})
            except Exception as e:
                logger.warning(f"Neo4j delete attraction texts failed: {e}")

        # 2.2) 删除景点簇（Attraction + 仅属于该景点的辐射节点）
        if attraction_ids:
            try:
                q_del_attractions = """
                UNWIND $ids AS aid
                MATCH (a:Attraction {id: aid})
                OPTIONAL MATCH (a)-[:HAS_FEATURE|HAS_HONOR|HAS_IMAGE|HAS_AUDIO]->(n)
                WITH a, collect(DISTINCT n) AS nodes
                FOREACH (x IN nodes |
                  FOREACH (_ IN CASE WHEN COUNT { (x)--() } <= 1 THEN [1] ELSE [] END |
                    DETACH DELETE x
                  )
                )
                WITH a
                OPTIONAL MATCH (a)-[r2:HAS_CATEGORY|位于]->()
                DELETE r2
                WITH a
                DETACH DELETE a
                """
                graph_builder.client.execute_query(q_del_attractions, {"ids": attraction_ids})
            except Exception as e:
                logger.warning(f"Neo4j delete attractions cluster failed: {e}")

        # 2.3) 删除知识 Text 节点（不逐条调用 _delete_knowledge_from_neo4j，改批量）
        if knowledge_text_ids:
            try:
                q_del_k_texts = """
                UNWIND $ids AS tid
                MATCH (t:Text {id: tid})
                OPTIONAL MATCH (t)-[r:MENTIONS]->()
                DELETE r
                WITH t
                OPTIONAL MATCH (t)-[r2:DESCRIBES]->()
                DELETE r2
                WITH t
                DETACH DELETE t
                """
                graph_builder.client.execute_query(q_del_k_texts, {"ids": knowledge_text_ids})
            except Exception as e:
                logger.warning(f"Neo4j delete knowledge texts failed: {e}")

        # 2.4) 删除景区簇（按 scenic_spot_id 精准清理）
        try:
            q_del_scenic_cluster = """
            MATCH (s:ScenicSpot {scenic_spot_id: $sid})
            OPTIONAL MATCH (s)-[r_loc:位于]->()
            DELETE r_loc
            WITH s
            OPTIONAL MATCH (s)-[r:HAS_SPOT|HAS_FEATURE|HAS_HONOR]->(n)
            WITH s, collect(DISTINCT n) AS nodes
            FOREACH (x IN nodes |
              FOREACH (_ IN CASE WHEN COUNT { (x)--() } <= 1 THEN [1] ELSE [] END |
                DETACH DELETE x
              )
            )
            WITH s
            OPTIONAL MATCH (s)-[r2:HAS_SPOT|HAS_FEATURE|HAS_HONOR]->()
            DELETE r2
            WITH s
            DETACH DELETE s
            """
            graph_builder.client.execute_query(q_del_scenic_cluster, {"sid": int(scenic_spot_id)})
        except Exception as e:
            logger.warning(f"Neo4j delete scenic cluster failed: {e}")

        # 3) PostgreSQL 批量删除
        # 3) PostgreSQL 强一致事务删除：景点/知识/景区 同一个事务中删除
        try:
            async with (await get_prisma()).tx() as tx:
                # attractions & knowledge 按 scenicSpotId 批删
                await tx.attraction.delete_many(where={"scenicSpotId": scenic_spot_id})
                await tx.knowledge.delete_many(where={"scenicSpotId": scenic_spot_id})
                tx_scenic_model = _get_prisma_model(tx, "scenicspot", "scenicSpot")
                await tx_scenic_model.delete(where={"id": scenic_spot_id})
        except Exception as e:
            logger.error(f"PG transactional delete for scenic_spot_id={scenic_spot_id} failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"删除景区及关联数据失败，请稍后重试: {e}")
        return {"message": "scenic spot deleted"}

    # 非级联：这里才会真正删除景区本身
    await scenic_model.delete(where={"id": scenic_spot_id})
    return {"message": "scenic spot deleted"}


@router.get("/scenic-spots/{scenic_spot_id}/knowledge", response_model=List[KnowledgeBaseItem])
async def list_scenic_spot_knowledge(
    scenic_spot_id: int,
    current_user: User = Depends(get_current_user),
):
    """获取某景区下的“景区总知识”列表（仅管理员）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    prisma = await get_prisma()
    rows = await prisma.knowledge.find_many(
        where={"scenicSpotId": scenic_spot_id},
        order={"id": "asc"},
        take=10000,
    )
    return [
        KnowledgeBaseItem(
            text_id=r.textId,
            text=r.text,
            metadata=_deserialize_metadata(r.metadata),
            scenic_spot_id=getattr(r, "scenicSpotId", None),
        )
        for r in rows
    ]


@router.post("/scenic-spots/{scenic_spot_id}/knowledge/upload")
async def upload_scenic_spot_knowledge(
    scenic_spot_id: int,
    items: List[KnowledgeBaseItem],
    collection_name: str = "tour_knowledge",
    build_graph: bool = True,
    current_user: User = Depends(get_current_user),
):
    """
    向指定景区上传“景区总知识”：
    - PG: Knowledge.scenicSpotId = scenic_spot_id
    - Milvus/Neo4j: 仍构建景区簇，但以该景区为准（允许自动解析+手动覆盖）
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")

    prisma = await get_prisma()
    scenic_model = _get_prisma_model(prisma, "scenicspot", "scenicSpot")
    scenic = await scenic_model.find_unique(where={"id": scenic_spot_id})
    if not scenic:
        raise HTTPException(status_code=404, detail="ScenicSpot not found")

    # 先同步到 GraphRAG（Milvus + Neo4j）
    # 为了保证“按景区一簇”，若解析出的 scenic_spot 不一致，则强制覆盖为当前景区名
    fixed_items: List[KnowledgeBaseItem] = []
    for it in items:
        fixed_items.append(
            KnowledgeBaseItem(
                text=it.text,
                text_id=it.text_id,
                metadata=it.metadata or {},
                scenic_spot_id=scenic_spot_id,
            )
        )

    # 同步：复用现有上传逻辑
    # 传入 scenic_spot_id + 景区名，确保 Neo4j 以 scenic_spot_id 为唯一键构建“一簇”
    result = await _upload_items_to_graphrag(
        fixed_items,
        collection_name,
        build_graph,
        scenic_name_override=str(scenic.name),
    )

    # 再持久化到 PostgreSQL（带 scenicSpotId）
    for it in fixed_items:
        meta_str = _serialize_metadata(it.metadata)
        await prisma.knowledge.upsert(
            where={"textId": it.text_id},
            data={
                "create": {
                    "textId": it.text_id,
                    "text": it.text,
                    "metadata": meta_str,
                    "scenicSpotId": scenic_spot_id,
                },
                "update": {
                    "text": it.text,
                    "metadata": meta_str,
                    "scenicSpotId": scenic_spot_id,
                },
            },
        )

    return result


@router.get("/scenic-spots/{scenic_spot_id}/attractions")
async def list_scenic_spot_attractions(
    scenic_spot_id: int,
    current_user: User = Depends(get_current_user),
):
    """获取某景区下的景点列表（仅管理员）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    prisma = await get_prisma()
    rows = await prisma.attraction.find_many(
        where={"scenicSpotId": scenic_spot_id},
        order={"id": "asc"},
        take=10000,
    )
    return [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "location": r.location,
            "latitude": r.latitude,
            "longitude": r.longitude,
            "category": r.category,
            "image_url": getattr(r, "imageUrl", None),
            "audio_url": getattr(r, "audioUrl", None),
            "scenic_spot_id": getattr(r, "scenicSpotId", None),
        }
        for r in rows
    ]


@router.post("/scenic-spots/{scenic_spot_id}/attractions")
async def create_scenic_spot_attraction(
    scenic_spot_id: int,
    req: AttractionAdminCreateRequest,
    current_user: User = Depends(get_current_user),
):
    """在指定景区下创建景点，并同步 GraphRAG（按簇）（仅管理员）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    prisma = await get_prisma()
    created = await prisma.attraction.create(
        data={
            "name": req.name,
            "description": req.description,
            "location": req.location,
            "latitude": req.latitude,
            "longitude": req.longitude,
            "category": req.category,
            "imageUrl": req.image_url,
            "audioUrl": req.audio_url,
            "scenicSpotId": scenic_spot_id,
        }
    )
    try:
        await _sync_attraction_to_graphrag(
            {
                "id": created.id,
                "name": created.name,
                "description": created.description,
                "location": created.location,
                "latitude": created.latitude,
                "longitude": created.longitude,
                "category": created.category,
                "image_url": getattr(created, "imageUrl", None),
                "audio_url": getattr(created, "audioUrl", None),
                "scenic_spot_id": scenic_spot_id,
            },
            operation="upsert",
        )
    except Exception:
        pass
    return {"id": created.id}


@router.put("/attractions/{attraction_id}")
async def update_attraction_admin(
    attraction_id: int,
    req: AttractionAdminUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    """更新景点并同步 GraphRAG（按簇）（仅管理员）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    prisma = await get_prisma()
    data = {}
    if req.name is not None:
        data["name"] = req.name
    if req.description is not None:
        data["description"] = req.description
    if req.location is not None:
        data["location"] = req.location
    if req.latitude is not None:
        data["latitude"] = req.latitude
    if req.longitude is not None:
        data["longitude"] = req.longitude
    if req.category is not None:
        data["category"] = req.category
    if req.image_url is not None:
        data["imageUrl"] = req.image_url
    if req.audio_url is not None:
        data["audioUrl"] = req.audio_url

    updated = await prisma.attraction.update(where={"id": attraction_id}, data=data)
    try:
        await _sync_attraction_to_graphrag(
            {
                "id": updated.id,
                "name": updated.name,
                "description": updated.description,
                "location": updated.location,
                "latitude": updated.latitude,
                "longitude": updated.longitude,
                "category": updated.category,
                "image_url": getattr(updated, "imageUrl", None),
                "audio_url": getattr(updated, "audioUrl", None),
                "scenic_spot_id": getattr(updated, "scenicSpotId", None),
            },
            operation="upsert",
        )
    except Exception:
        pass
    return {"message": "updated"}


@router.delete("/attractions/{attraction_id}")
async def delete_attraction_admin(attraction_id: int, current_user: User = Depends(get_current_user)):
    """删除景点并按簇清理 GraphRAG（仅管理员）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    prisma = await get_prisma()
    existing = await prisma.attraction.find_unique(where={"id": attraction_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Attraction not found")
    try:
        await _sync_attraction_to_graphrag(
            {
                "id": existing.id,
                "name": existing.name,
                "description": existing.description,
                "location": existing.location,
                "latitude": existing.latitude,
                "longitude": existing.longitude,
                "category": existing.category,
                "image_url": getattr(existing, "imageUrl", None),
                "audio_url": getattr(existing, "audioUrl", None),
                "scenic_spot_id": getattr(existing, "scenicSpotId", None),
            },
            operation="delete",
        )
    except Exception:
        pass
    await prisma.attraction.delete(where={"id": attraction_id})
    return {"message": "deleted"}

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
                    collection = milvus_client.get_collection(collection_name, load=True)
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
                # 按“簇”删除：只删除属于该景点的辐射节点（Feature/Honor/Image/Audio），位置/类别节点保留
                query = """
                MATCH (a:Attraction {id: $id})
                OPTIONAL MATCH (a)-[r:HAS_FEATURE|HAS_HONOR|HAS_IMAGE|HAS_AUDIO]->(n)
                DETACH DELETE n
                WITH a
                OPTIONAL MATCH (a)-[r2:HAS_CATEGORY|位于|属于]->(x)
                DELETE r2
                WITH a
                DETACH DELETE a
                """
                graph_builder.client.execute_query(query, {"id": int(attraction_dict.get('id'))})
                logger.info(f"已从 Neo4j 按簇删除景点节点: {attraction_dict.get('id')}")
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
                # 统一走“以景点为中心的一簇”：
                # - 中心节点：(:Attraction {id})
                # - 辐射节点：Feature/Honor/Category/Image/Audio/位置链
                # - Text 只作为可选关联，不再生成散点 MENTIONS
                parsed = None
                try:
                    parsed = await rag_service.parse_attraction_text(attraction_dict.get("name") or "", text)
                except Exception as e:
                    logger.debug(f"parse_attraction_text failed for attraction_id={attraction_dict.get('id')}: {e}")

                await graph_builder.build_attraction_cluster(
                    attraction_dict,
                    text_id=text_id,
                    text=text,
                    parsed=parsed,
                )
                logger.info(f"已按簇更新 Neo4j 中的景点: {text_id}")
            except Exception as e:
                logger.error(f"更新 Neo4j 失败: {e}")
                raise
            
            # 旧逻辑：create_attraction_node + extract_and_store_entities
            # 已由 build_attraction_cluster 统一覆盖
        
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
            collection = milvus_client.get_collection(collection_name, load=True)
            expr = f'text_id == "{text_id}"'
            collection.delete(expr)
            collection.flush()
            logger.info(f"已从 Milvus 删除知识库: {text_id}")
    except Exception as e:
        logger.warning(f"从 Milvus 删除失败: {e}")


async def _delete_text_ids_from_milvus(text_ids: List[str], collection_name: str = "tour_knowledge") -> None:
    """从 Milvus 批量删除多个 text_id（分块 + 尽量一次 flush）"""
    if not text_ids:
        return
    try:
        from pymilvus import utility
        if not utility.has_collection(collection_name):
            return
        collection = milvus_client.get_collection(collection_name, load=True)

        # Milvus 对 expr 长度有限制；分块拼接 OR
        chunk_size = 200
        for i in range(0, len(text_ids), chunk_size):
            chunk = text_ids[i : i + chunk_size]
            parts = [f'text_id == "{tid}"' for tid in chunk]
            expr = " or ".join(parts)
            collection.delete(expr)

        collection.flush()
        try:
            rag_service._milvus_loaded_collections.add(collection_name)
        except Exception:
            pass
        logger.info(f"已从 Milvus 批量删除 text_id 数量: {len(text_ids)}")
    except Exception as e:
        logger.warning(f"Milvus 批量删除失败: {e}")


async def _delete_knowledge_from_neo4j(text_id: str) -> None:
    """从 Neo4j 删除指定 text_id 的 Text 节点及其关联的景区簇（如果该景区不再被其他 Text 描述）"""
    try:
        # 1) 先查找该 Text 节点描述的景区，并检查是否还有其他 Text 节点描述该景区
        #    注意：必须在删除 Text 节点之前检查，否则无法正确判断
        query_check = """
        MATCH (t:Text {id: $text_id})-[:DESCRIBES]->(s:ScenicSpot)
        OPTIONAL MATCH (s)<-[:DESCRIBES]-(other:Text)
        WITH s,
             collect(DISTINCT other.id) AS other_text_ids
        WITH
          s.scenic_spot_id AS scenic_spot_id,
          s.name AS scenic_name,
          [tid IN other_text_ids WHERE tid <> $text_id] AS remaining_text_ids
        RETURN scenic_spot_id, scenic_name, remaining_text_ids
        """
        result = graph_builder.client.execute_query(query_check, {"text_id": text_id})
        
        # 2) 删除 Text 节点本身
        query_text = """
        MATCH (t:Text {id: $text_id})
        OPTIONAL MATCH (t)-[r1:MENTIONS]->(e)
        DELETE r1
        WITH t
        OPTIONAL MATCH (t)-[r2:DESCRIBES]->(s:ScenicSpot)
        DELETE r2
        WITH t
        DETACH DELETE t
        """
        graph_builder.client.execute_query(query_text, {"text_id": text_id})
        
        # 3) 如果该景区没有其他 Text 节点描述，删除整个景区簇
        if result and len(result) > 0:
            for row in result:
                remaining_text_ids = row.get("remaining_text_ids", [])
                # 过滤掉 None 值
                remaining_text_ids = [tid for tid in remaining_text_ids if tid is not None]
                
                # 如果没有其他 Text 节点描述该景区，删除整个簇
                if len(remaining_text_ids) == 0:
                    scenic_id = row.get("scenic_spot_id", None)
                    scenic_name = row.get("scenic_name", None)
                    if scenic_id is None:
                        # 兼容旧数据：没有 scenic_spot_id 时兜底按 name 删除“无 Text 描述”的簇
                        if scenic_name:
                            scenic_id = None
                        else:
                            query_delete_all = """
                            MATCH (s:ScenicSpot)
                            WHERE NOT EXISTS { (s)<-[:DESCRIBES]-(:Text) }
                            OPTIONAL MATCH (s)-[r]-(n)
                            DETACH DELETE s, n
                            """
                            graph_builder.client.execute_query(query_delete_all)
                            logger.info("已删除所有无 Text 节点描述的景区簇")
                            continue

                    if scenic_id is not None:
                        # 按 scenic_spot_id 删除整簇（Spot/Feature/Honor 视为该簇专属，可清理）
                        query_delete_cluster = """
                        MATCH (s:ScenicSpot {scenic_spot_id: $sid})
                        // 1) 先断开位置关系（位置节点可能共享）
                        OPTIONAL MATCH (s)-[r_loc:位于]->(loc)
                        DELETE r_loc
                        WITH s
                        // 2) 删除簇内节点（Spot/Feature/Honor）仅当它们不再与任何其他节点相连
                        OPTIONAL MATCH (s)-[r1:HAS_SPOT|HAS_FEATURE|HAS_HONOR]->(n)
                        WITH s, collect(DISTINCT n) AS nodes
                        FOREACH (x IN nodes |
                          FOREACH (_ IN CASE WHEN COUNT { (x)--() } <= 1 THEN [1] ELSE [] END |
                            DETACH DELETE x
                          )
                        )
                        WITH s
                        // 3) 删除剩余关系并删除景区节点
                        OPTIONAL MATCH (s)-[r2:HAS_SPOT|HAS_FEATURE|HAS_HONOR]->(n2)
                        DELETE r2
                        WITH s
                        DETACH DELETE s
                        """
                        graph_builder.client.execute_query(query_delete_cluster, {"sid": int(scenic_id)})
                        logger.info(f"已完整删除景区簇: {scenic_name or scenic_id}")
                    elif scenic_name:
                        # 旧数据按 name 删除
                        query_delete_cluster_legacy = """
                        MATCH (s:ScenicSpot {name: $name})
                        OPTIONAL MATCH (s)-[r_loc:位于]->(loc)
                        DELETE r_loc
                        WITH s
                        OPTIONAL MATCH (s)-[r1:HAS_SPOT|HAS_FEATURE|HAS_HONOR]->(n)
                        WITH s, collect(DISTINCT n) AS nodes
                        FOREACH (x IN nodes |
                          FOREACH (_ IN CASE WHEN COUNT { (x)--() } <= 1 THEN [1] ELSE [] END |
                            DETACH DELETE x
                          )
                        )
                        WITH s
                        OPTIONAL MATCH (s)-[r2:HAS_SPOT|HAS_FEATURE|HAS_HONOR]->(n2)
                        DELETE r2
                        WITH s
                        DETACH DELETE s
                        """
                        graph_builder.client.execute_query(query_delete_cluster_legacy, {"name": scenic_name})
                        logger.info(f"已完整删除景区簇(legacy): {scenic_name}")
                else:
                    logger.info(f"景区仍有其他 Text 节点描述（{len(remaining_text_ids)} 个），保留景区簇")
        
        logger.info(f"已从 Neo4j 删除知识库及景区簇（如适用）: {text_id}")
    except Exception as e:
        logger.warning(f"从 Neo4j 删除失败: {e}", exc_info=True)


async def _upload_items_to_graphrag(
    items: List[KnowledgeBaseItem],
    collection_name: str,
    build_graph: bool,
    scenic_name_override: str | None = None,
) -> dict:
    """复用 /admin/knowledge/upload 的逻辑，供批量导入调用。"""
    # 步骤1: 创建集合（如果不存在）
    collection = milvus_client.create_collection_if_not_exists(
        collection_name,
        dimension=384
    )

    # 步骤2: 生成嵌入向量并存储到 Milvus
    texts = [item.text for item in items]
    # 避免阻塞事件循环：embedding 生成放到线程池 + 批量 encode
    embeddings = await asyncio.to_thread(rag_service.generate_embeddings_batch, texts)

    # 准备数据（与 milvus schema: [text_id, embedding]）
    entities = [
        [item.text_id for item in items],
        embeddings
    ]

    # 先删除旧数据（避免重复 text_id 产生多条）
    try:
        # Milvus 表达式对 VARCHAR 的 IN 支持依赖版本；这里保守逐条 delete，最后 flush 一次
        for tid in entities[0]:
            collection.delete(f'text_id == "{tid}"')
    except Exception as e:
        logger.warning(f"Milvus pre-delete failed (will still insert): {e}")

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
                await graph_builder.build_scenic_cluster(
                    parsed,
                    text_id=item.text_id,
                    scenic_spot_id=item.scenic_spot_id,
                    scenic_name_override=scenic_name_override,
                )
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

        # 再持久化到 PostgreSQL（Prisma），并自动归类到 ScenicSpot（可手动覆盖 scenic_spot_id）
        prisma = await get_prisma()
        scenic_model = _get_prisma_model(prisma, "scenicspot", "scenicSpot")
        for item in items:
            if not item.text_id:
                continue
            try:
                meta_str = _serialize_metadata(item.metadata)
                scenic_spot_id = item.scenic_spot_id

                # 自动识别景区：如果未手动指定 scenic_spot_id，则尝试从文本解析
                if scenic_spot_id is None:
                    try:
                        parsed = await rag_service.parse_scenic_text(item.text)
                        if parsed and parsed.get("scenic_spot"):
                            scenic_name = str(parsed.get("scenic_spot")).strip()
                            scenic = await scenic_model.upsert(
                                where={"name": scenic_name},
                                data={
                                    "create": {"name": scenic_name, "location": "、".join(parsed.get("location") or []) or None},
                                    "update": {"location": "、".join(parsed.get("location") or []) or None},
                                },
                            )
                            scenic_spot_id = scenic.id
                    except Exception:
                        pass

                await prisma.knowledge.upsert(
                    where={"textId": item.text_id},
                    data={
                        "create": {
                            "textId": item.text_id,
                            "text": item.text,
                            "metadata": meta_str,
                            "scenicSpotId": scenic_spot_id,
                        },
                        "update": {
                            "text": item.text,
                            "metadata": meta_str,
                            "scenicSpotId": scenic_spot_id,
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
            scenic_spot_id=getattr(row, "scenicSpotId", None),
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


@router.post("/knowledge/migrate-neo4j-scenic-spots")
async def migrate_neo4j_scenic_spots(
    current_user: User = Depends(get_current_user),
    dry_run: bool = False,
):
    """
    一键把 Neo4j 里旧的 ScenicSpot（仅 name、无 scenic_spot_id）迁移到新结构：
    - ScenicSpot 唯一键：scenic_spot_id（对应 PostgreSQL ScenicSpot.id）
    - 子景点关系：HAS_ATTRACTION -> HAS_SPOT，并把子节点 label 从 :Attraction(name) 迁为 :Spot(name)
    - 迁移 DESCRIBES/位于/HAS_FEATURE/HAS_HONOR 等关系到新 ScenicSpot 节点
    - 最后清理旧 ScenicSpot 节点（无 scenic_spot_id）
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")

    prisma = await get_prisma()
    scenic_model = _get_prisma_model(prisma, "scenicspot", "scenicSpot")
    # 分批拉取，避免一次性 take=100000
    scenic_rows = []
    skip = 0
    batch = 1000
    while True:
        part = await scenic_model.find_many(order={"id": "asc"}, skip=skip, take=batch)
        if not part:
            break
        scenic_rows.extend(part)
        skip += len(part)

    spots_payload = []
    for s in scenic_rows:
        name = getattr(s, "name", None)
        if not name:
            continue
        spots_payload.append(
            {
                "id": int(s.id),
                "name": str(name),
                "aliases": list({str(name).strip(), _normalize_scenic_name(str(name))}),
            }
        )

    # 迁移：UNWIND PG 景区列表，按 name/alias 匹配 Neo4j 旧节点并搬迁关系
    q_migrate = """
    UNWIND $spots AS sp
    WITH sp
    MATCH (old:ScenicSpot)
    WHERE (old.scenic_spot_id IS NULL OR old.scenic_spot_id = 0)
      AND old.name IN sp.aliases
    MERGE (s:ScenicSpot {scenic_spot_id: sp.id})
    SET s.name = sp.name

    // 1) 迁移 Text -> ScenicSpot（DESCRIBES）
    OPTIONAL MATCH (t:Text)-[r_desc:DESCRIBES]->(old)
    FOREACH (_ IN CASE WHEN t IS NULL THEN [] ELSE [1] END |
      MERGE (t)-[:DESCRIBES]->(s)
      DELETE r_desc
    )

    // 2) 迁移位置关系（位于），位置节点可能共享，只迁移关系
    OPTIONAL MATCH (old)-[r_loc:位于]->(loc)
    FOREACH (_ IN CASE WHEN loc IS NULL THEN [] ELSE [1] END |
      MERGE (s)-[:位于]->(loc)
      DELETE r_loc
    )

    // 3) 迁移 Feature/Honor（直接搬关系）
    OPTIONAL MATCH (old)-[r_f:HAS_FEATURE]->(f:Feature)
    FOREACH (_ IN CASE WHEN f IS NULL THEN [] ELSE [1] END |
      MERGE (s)-[:HAS_FEATURE]->(f)
      DELETE r_f
    )
    OPTIONAL MATCH (old)-[r_h:HAS_HONOR]->(h:Honor)
    FOREACH (_ IN CASE WHEN h IS NULL THEN [] ELSE [1] END |
      MERGE (s)-[:HAS_HONOR]->(h)
      DELETE r_h
    )

    // 4) 迁移旧的“子景点”关系：HAS_ATTRACTION -> HAS_SPOT，并把节点 label 统一为 :Spot
    OPTIONAL MATCH (old)-[r_a:HAS_ATTRACTION]->(a)
    FOREACH (_ IN CASE WHEN a IS NULL THEN [] ELSE [1] END |
      FOREACH (__ IN CASE WHEN 'Attraction' IN labels(a) THEN [1] ELSE [] END |
        REMOVE a:Attraction
        SET a:Spot
      )
      MERGE (s)-[:HAS_SPOT]->(a)
      DELETE r_a
    )

    // 5) 迁移旧版里如果已经有 HAS_SPOT，也统一搬过来
    OPTIONAL MATCH (old)-[r_sp:HAS_SPOT]->(spn)
    FOREACH (_ IN CASE WHEN spn IS NULL THEN [] ELSE [1] END |
      MERGE (s)-[:HAS_SPOT]->(spn)
      DELETE r_sp
    )

    WITH old, s
    RETURN count(DISTINCT old) AS matched_old, count(DISTINCT s) AS ensured_new
    """

    # 清理：删除所有“无 scenic_spot_id 且已没有任何关系”的旧 ScenicSpot
    q_cleanup = """
    MATCH (old:ScenicSpot)
    WHERE old.scenic_spot_id IS NULL OR old.scenic_spot_id = 0
    WITH old, COUNT { (old)--() } AS deg
    WHERE deg = 0
    DETACH DELETE old
    RETURN count(*) AS deleted
    """

    if dry_run:
        # 只返回将要处理的数量（粗略统计：匹配旧节点数量）
        q_preview = """
        UNWIND $spots AS sp
        MATCH (old:ScenicSpot)
        WHERE (old.scenic_spot_id IS NULL OR old.scenic_spot_id = 0)
          AND old.name IN sp.aliases
        RETURN count(DISTINCT old) AS would_match
        """
        preview = graph_builder.client.execute_query(q_preview, {"spots": spots_payload})
        return {"dry_run": True, "would_match": (preview[0].get("would_match") if preview else 0)}

    migrated = graph_builder.client.execute_query(q_migrate, {"spots": spots_payload})
    cleaned = graph_builder.client.execute_query(q_cleanup)
    return {
        "message": "migrated",
        "matched_old": (migrated[0].get("matched_old") if migrated else 0),
        "ensured_new": (migrated[0].get("ensured_new") if migrated else 0),
        "deleted_old_isolated": (cleaned[0].get("deleted") if cleaned else 0),
    }


@router.post("/knowledge/clear-vector")
async def clear_vector_database(
    collection_name: str = "tour_knowledge",
    current_user: User = Depends(get_current_user),
):
    """
    清空 Milvus 向量数据库的指定 collection 中的所有数据（保留集合结构，危险操作，仅管理员）
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    
    try:
        from pymilvus import utility
        
        if not milvus_client.connected:
            milvus_client.connect()
        
        if not utility.has_collection(collection_name):
            return {"message": f"Collection {collection_name} 不存在，无需清空"}
        
        # 获取集合并加载（删除操作需要集合已加载）
        collection = milvus_client.get_collection(collection_name, load=True)
        
        # 删除所有数据（使用 LIKE '%' 表达式匹配所有 text_id）
        # 参考 clear_milvus.py 的实现方式
        expr = "text_id like '%'"
        collection.delete(expr)
        collection.flush()
        try:
            rag_service._milvus_loaded_collections.discard(collection_name)
        except Exception:
            pass
        logger.info(f"已清空 Milvus collection '{collection_name}' 中的所有数据（集合结构已保留）")
        
        return {
            "message": f"已清空向量数据库（collection: {collection_name}，集合结构已保留）",
            "collection_name": collection_name,
            "action": "cleared_data_only"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"清空向量数据库失败: {e}")
        raise HTTPException(status_code=500, detail=f"清空失败: {str(e)}")


@router.post("/knowledge/load-collection")
async def load_collection(
    collection_name: str = "tour_knowledge",
    current_user: User = Depends(get_current_user),
):
    """
    加载 Milvus 集合到内存（用于 Attu 刷新后重新加载集合）
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    
    try:
        from pymilvus import utility
        
        if not milvus_client.connected:
            milvus_client.connect()
        
        if not utility.has_collection(collection_name):
            raise HTTPException(status_code=404, detail=f"Collection {collection_name} 不存在")
        
        # 获取集合并加载
        collection = milvus_client.get_collection(collection_name, load=False)
        
        # 检查当前加载状态
        try:
            load_state = utility.load_state(collection_name)
            logger.info(f"Collection '{collection_name}' current load state: {load_state}")
        except Exception as e:
            logger.warning(f"Failed to check load state: {e}")
        
        # 加载集合
        collection.load()
        logger.info(f"Collection '{collection_name}' loaded successfully")
        try:
            rag_service._milvus_loaded_collections.add(collection_name)
        except Exception:
            pass
        
        return {
            "message": f"Collection {collection_name} 已加载到内存",
            "collection_name": collection_name,
            "status": "loaded"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"加载集合失败: {e}")
        raise HTTPException(status_code=500, detail=f"加载失败: {str(e)}")

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


@router.get("/analytics/rag-logs")
async def get_rag_logs(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    管理员查看最近的 RAG 检索上下文日志：
    - 每次问答时从向量库和图数据库检索出的内容（enhanced_context）
    - 命中的向量结果 / 图结果（前若干条）
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可查看 RAG 日志")

    logs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    log_path = os.path.join(logs_dir, "rag_context.log")
    if not os.path.exists(log_path):
        return []

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        logger.error(f"读取 RAG 日志失败: {e}")
        raise HTTPException(status_code=500, detail="读取 RAG 日志失败")

    entries: List[Dict[str, Any]] = []
    # 取最后 limit 条（从文件尾部往前）
    for line in reversed(lines[-limit:]):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            entries.append(
                {
                    "timestamp": data.get("timestamp", ""),
                    "query": data.get("query", ""),
                    "final_answer_preview": data.get("final_answer_preview", ""),
                    "use_rag": bool(data.get("use_rag", False)),
                    "rag_debug": data.get("rag_debug") or {},
                }
            )
        except Exception:
            continue

    # 由于是从文件尾部向前遍历，最后需要再反转一次，让最新的在最上面
    return list(reversed(entries))

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
    
    # 将 SQLAlchemy 返回的 Row/元组转换为普通字典，方便 FastAPI 编码为 JSON
    popular_list = [
        {
            "id": row[0],
            "name": row[1],
            "visit_count": int(row[2] or 0),
        }
        for row in popular
    ]
    
    return {"popular_attractions": popular_list}

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

