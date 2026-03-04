"""知识图谱构建：文本 -> Neo4j 图结构。"""
import logging
import asyncio
from typing import List, Dict, Any
from app.core.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)


class GraphBuilder:
    """将文本知识转为图结构并写入 Neo4j。"""

    def __init__(self):
        self.client = neo4j_client

    async def _execute_query_async(self, query: str, parameters: Dict[str, Any] | None = None):
        """
        在异步上下文中安全执行 Neo4j 查询，避免阻塞事件循环。
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.client.execute_query,
            query,
            parameters or {},
        )
    
    async def create_attraction_node(self, attraction_data: Dict[str, Any]) -> bool:
        """创建景点节点"""
        query = """
        MERGE (a:Attraction {id: $id})
        SET a.name = $name,
            a.description = $description,
            a.location = $location,
            a.latitude = $latitude,
            a.longitude = $longitude,
            a.category = $category
        RETURN a
        """
        
        try:
            await self._execute_query_async(query, attraction_data)
            logger.info(f"Created attraction node: {attraction_data.get('name')}")
            return True
        except Exception as e:
            logger.error(f"Failed to create attraction node: {e}")
            return False

    async def build_attraction_cluster(
        self,
        attraction_data: Dict[str, Any],
        text_id: str | None = None,
        text: str | None = None,
        parsed: Dict[str, Any] | None = None,
    ) -> None:
        """以单景点为中心构建一簇（Attraction + 辐射节点）。"""
        if not attraction_data:
            return
        att_id = attraction_data.get("id")
        if att_id is None:
            return
        name = attraction_data.get("name") or ""
        name = str(name).strip()
        if not name:
            return
        scenic_spot_id = attraction_data.get("scenic_spot_id")

        # 从解析结果中尝试提取景区名称，作为补充的“簇中心”
        scenic_name_from_parsed = None
        if parsed and isinstance(parsed, dict) and parsed.get("scenic_spot"):
            try:
                scenic_name_from_parsed = str(parsed.get("scenic_spot")).strip() or None
            except Exception:
                scenic_name_from_parsed = None

        # 硬性约束：若既没有景区 ID，也解析不出景区名称，则完全跳过图构建，
        # 以避免出现“只有景点/特征的小游离簇”
        if not scenic_spot_id and not scenic_name_from_parsed:
            logger.warning(
                "build_attraction_cluster: 缺少景区上下文(scenic_spot_id / scenic_spot 名称)，"
                "已跳过图构建以避免游离节点: id=%s, name=%s",
                att_id,
                name,
            )
            return

        q_center = """
        MERGE (a:Attraction {id: $id})
        SET a.name = $name,
            a.description = $description,
            a.location = $location,
            a.latitude = $latitude,
            a.longitude = $longitude,
            a.category = $category,
            a.image_url = $image_url,
            a.audio_url = $audio_url,
            a.scenic_spot_id = $scenic_spot_id
        """
        await self._execute_query_async(q_center, {
            "id": int(att_id),
            "name": name,
            "description": attraction_data.get("description"),
            "location": attraction_data.get("location"),
            "latitude": attraction_data.get("latitude"),
            "longitude": attraction_data.get("longitude"),
            "category": attraction_data.get("category"),
            "image_url": attraction_data.get("image_url"),
            "audio_url": attraction_data.get("audio_url"),
            "scenic_spot_id": int(scenic_spot_id) if scenic_spot_id else None,
        })
        q_clean_rels = """
        MATCH (a:Attraction {id: $id})-[r:HAS_CATEGORY|HAS_FEATURE|HAS_HONOR|HAS_IMAGE|HAS_AUDIO|位于|属于]->(n)
        DELETE r
        """
        await self._execute_query_async(q_clean_rels, {"id": int(att_id)})
        q_clean_orphans = """
        MATCH (a:Attraction {id: $id})-[r:HAS_FEATURE|HAS_HONOR|HAS_IMAGE|HAS_AUDIO]->(n)
        WITH n, COUNT { (n)--() } AS c
        WHERE c <= 1
        DETACH DELETE n
        """
        await self._execute_query_async(q_clean_orphans, {"id": int(att_id)})

        # 统一约束：无论景区来自 PostgreSQL 还是解析结果，Attraction 必须挂到某个 ScenicSpot 上，
        # 从而保证不会出现完全脱离景区簇的景点子图。
        if scenic_spot_id:
            q_scenic_rel = """
            MATCH (a:Attraction {id: $id})
            MATCH (s:ScenicSpot {scenic_spot_id: $scenic_spot_id})
            MERGE (a)-[:属于]->(s)
            """
            await self._execute_query_async(q_scenic_rel, {
                "id": int(att_id),
                "scenic_spot_id": int(scenic_spot_id)
            })
            logger.info(f"景点 '{name}' (Attraction, id={att_id}) 已关联到景区 (scenic_spot_id={scenic_spot_id})")
            q_merge_spot = """
            MATCH (s:ScenicSpot {scenic_spot_id: $scenic_spot_id})
            OPTIONAL MATCH (s)-[r:HAS_SPOT]->(sp:Spot {name: $name})
            WITH s, r, sp
            MATCH (a:Attraction {id: $id})
            // 确保景区仍然通过 HAS_SPOT 指向“正式的景点”节点
            MERGE (s)-[:HAS_SPOT]->(a)
            // 如果之前存在同名 Spot，则删除旧的 Spot 节点及其关系
            FOREACH (_ IN CASE WHEN sp IS NULL THEN [] ELSE [1] END |
              DETACH DELETE sp
            )
            """
            try:
                await self._execute_query_async(q_merge_spot, {
                    "id": int(att_id),
                    "scenic_spot_id": int(scenic_spot_id),
                    "name": name,
                })
            except Exception as e:
                logger.warning(f"合并景区子景点 Spot -> Attraction 失败: {e}")
        elif scenic_name_from_parsed:
            # 没有 scenic_spot_id，但解析出了景区名称：在图中按名称作为“景区主节点”挂接，
            # 仍然保证整个簇围绕 ScenicSpot 汇聚，而不是形成独立小簇
            q_ensure_scenic_by_name = """
            MERGE (s:ScenicSpot {name: $name})
            ON CREATE SET s.scenic_spot_id = coalesce(s.scenic_spot_id, 0)
            RETURN s
            """
            try:
                await self._execute_query_async(q_ensure_scenic_by_name, {
                    "name": scenic_name_from_parsed,
                })
            except Exception as e:
                logger.warning(f"按名称确保 ScenicSpot 节点失败: {e}")
            q_scenic_rel_by_name = """
            MATCH (a:Attraction {id: $id})
            MATCH (s:ScenicSpot {name: $name})
            MERGE (a)-[:属于]->(s)
            MERGE (s)-[:HAS_SPOT]->(a)
            """
            try:
                await self._execute_query_async(q_scenic_rel_by_name, {
                    "id": int(att_id),
                    "name": scenic_name_from_parsed,
                })
                logger.info(
                    "景点 '%s' (Attraction, id=%s) 已通过解析名称挂接到景区 '%s'",
                    name,
                    att_id,
                    scenic_name_from_parsed,
                )
            except Exception as e:
                logger.warning(f"按名称关联景点到景区失败: {e}")
        if text_id and text:
            q_text = """
            MERGE (t:Text {id: $text_id})
            SET t.content = $text
            WITH t
            MATCH (a:Attraction {id: $id})
            MERGE (t)-[:DESCRIBES]->(a)
            """
            await self._execute_query_async(q_text, {"text_id": text_id, "text": text, "id": int(att_id)})
        locations = []
        if parsed and isinstance(parsed.get("location"), list):
            locations = [str(x).strip() for x in parsed.get("location") if str(x).strip()]
        if not locations:
            loc_raw = attraction_data.get("location") or ""
            loc_raw = str(loc_raw)
            for sep in [" ", "，", "、", ",", "/", "-", "—", "·"]:
                loc_raw = loc_raw.replace(sep, " ")
            parts = [p.strip() for p in loc_raw.split(" ") if p.strip()]
            locations = [p for p in parts if any(p.endswith(s) for s in ["省", "市", "县", "区", "旗", "州"])]
        q_clean_loc = """
        MATCH (a:Attraction {id: $id})-[r:位于]->()
        DELETE r
        """
        await self._execute_query_async(q_clean_loc, {"id": int(att_id)})
        if locations:
            params = {"id": int(att_id)}
            if len(locations) >= 3:
                q_loc_nodes = """
                MERGE (prov:Province {name: $prov})
                MERGE (city:City {name: $city})
                MERGE (county:County {name: $county})
                MERGE (city)-[:隶属]->(prov)
                MERGE (county)-[:隶属]->(city)
                """
                params.update({"prov": locations[0], "city": locations[1], "county": locations[2]})
                await self._execute_query_async(q_loc_nodes, params)
                q_loc_rel = """
                MATCH (a:Attraction {id: $id})
                MATCH (county:County {name: $county})
                MERGE (a)-[:位于]->(county)
                """
                await self._execute_query_async(q_loc_rel, params)
            elif len(locations) == 2:
                q_loc_nodes = """
                MERGE (prov:Province {name: $prov})
                MERGE (city:City {name: $city})
                MERGE (city)-[:隶属]->(prov)
                """
                params.update({"prov": locations[0], "city": locations[1]})
                await self._execute_query_async(q_loc_nodes, params)
                q_loc_rel = """
                MATCH (a:Attraction {id: $id})
                MATCH (city:City {name: $city})
                MERGE (a)-[:位于]->(city)
                """
                await self._execute_query_async(q_loc_rel, params)
            elif len(locations) == 1:
                q_loc_nodes = """
                MERGE (prov:Province {name: $prov})
                """
                params.update({"prov": locations[0]})
                await self._execute_query_async(q_loc_nodes, params)
                q_loc_rel = """
                MATCH (a:Attraction {id: $id})
                MATCH (prov:Province {name: $prov})
                MERGE (a)-[:位于]->(prov)
                """
                await self._execute_query_async(q_loc_rel, params)
        category = (parsed.get("category") if parsed else None) or attraction_data.get("category")
        if category:
            q_cat = """
            MATCH (a:Attraction {id: $id})
            MERGE (c:Category {name: $name})
            MERGE (a)-[:HAS_CATEGORY]->(c)
            """
            await self._execute_query_async(q_cat, {"id": int(att_id), "name": str(category).strip()})
        if attraction_data.get("image_url"):
            q_img = """
            MATCH (a:Attraction {id: $id})
            MERGE (img:Image {url: $url})
            MERGE (a)-[:HAS_IMAGE]->(img)
            """
            await self._execute_query_async(q_img, {"id": int(att_id), "url": attraction_data.get("image_url")})
        if attraction_data.get("audio_url"):
            q_audio = """
            MATCH (a:Attraction {id: $id})
            MERGE (au:Audio {url: $url})
            MERGE (a)-[:HAS_AUDIO]->(au)
            """
            await self._execute_query_async(q_audio, {"id": int(att_id), "url": attraction_data.get("audio_url")})
        features = (parsed.get("features") if parsed else None) or []
        honors = (parsed.get("honors") if parsed else None) or []
        if isinstance(features, list):
            feats = [str(x).strip() for x in features if str(x).strip()]
            if feats:
                q_f = """
                UNWIND $features AS fname
                MATCH (a:Attraction {id: $id})
                // 为避免景点之间因共用 Feature 节点而产生间接“连通”，
                // 这里按 (name, attraction_id) 作为唯一键，为每个景点创建自己的 Feature 节点。
                MERGE (f:Feature {name: fname, attraction_id: $id})
                MERGE (a)-[:HAS_FEATURE]->(f)
                """
                await self._execute_query_async(q_f, {"id": int(att_id), "features": feats})
        if isinstance(honors, list):
            hns = [str(x).strip() for x in honors if str(x).strip()]
            if hns:
                q_h = """
                UNWIND $honors AS hname
                MATCH (a:Attraction {id: $id})
                // 同理，按 (name, attraction_id) 唯一，避免不同景点通过共用 Honor 节点相连
                MERGE (h:Honor {name: hname, attraction_id: $id})
                MERGE (a)-[:HAS_HONOR]->(h)
                """
                await self._execute_query_async(q_h, {"id": int(att_id), "honors": hns})
    
    async def create_relationship(self, from_entity: str, to_entity: str, 
                                 relation_type: str, properties: Dict = None) -> bool:
        """创建实体之间的关系"""
        # 关系类型做简单的白名单校验，避免 Cypher 注入
        import re
        rel = None
        if relation_type and isinstance(relation_type, str):
            candidate = relation_type.strip().upper()
            if re.match(r"^[A-Z_][A-Z0-9_]*$", candidate):
                rel = candidate
        if not rel:
            logger.error(f"Invalid relation_type: {relation_type}")
            return False

        query = f"""
        MATCH (a), (b)
        WHERE a.name = $from_name AND b.name = $to_name
        MERGE (a)-[r:{rel}]->(b)
        """
        
        if properties:
            set_clauses = [f"r.{k} = ${k}" for k in properties.keys()]
            query += " SET " + ", ".join(set_clauses)
        
        query += " RETURN r"
        
        params = {
            "from_name": from_entity,
            "to_name": to_entity,
            **(properties or {})
        }
        
        try:
            await self._execute_query_async(query, params)
            logger.info(f"Created relationship: {from_entity} -[{relation_type}]-> {to_entity}")
            return True
        except Exception as e:
            logger.error(f"Failed to create relationship: {e}")
            return False
    
    async def build_attraction_graph(self, attractions: List[Dict[str, Any]]):
        """
        批量构建景点图谱。
        要求：所有景点簇必须连接到某个景区簇，且景点之间**不再直接建立关系**。
        因此，这里仅调用 build_attraction_cluster 为每个景点补全自身簇，
        并确保通过“属于 / HAS_SPOT”挂接到对应 ScenicSpot。
        Attraction 之间不再创建 NEARBY 等边。
        """
        # 为每个景点构建“以景区为中心”的景点簇
        for attraction in attractions:
            scenic_spot_id = attraction.get("scenic_spot_id")
            if not scenic_spot_id:
                logger.warning(
                    "build_attraction_graph: attraction id=%s name=%s 缺少 scenic_spot_id，"
                    "为避免游离簇，跳过该景点的簇构建",
                    attraction.get("id"),
                    attraction.get("name"),
                )
                continue
            try:
                await self.build_attraction_cluster(
                    attraction_data=attraction,
                    text_id=None,
                    text=None,
                    parsed=None,
                )
            except Exception as e:
                logger.error(
                    "build_attraction_graph: 构建景点簇失败 id=%s name=%s: %s",
                    attraction.get("id"),
                    attraction.get("name"),
                    e,
                )
    
    async def extract_and_store_entities(
        self,
        text: str,
        text_id: str,
        entities: List[Dict[str, Any]],
        scenic_spot_id: int | None = None,
        scenic_name: str | None = None,
    ):
        """
        从文本中提取实体并存储到图数据库。
        必须围绕景区簇添加关系：所有节点（Text、Entity）均连接到 ScenicSpot，不得出现离散节点。
        若未提供 scenic_spot_id 或 scenic_name，则不创建图（避免孤儿节点）。
        """
        # 必须有景区上下文，否则不创建图，避免离散节点
        use_id = scenic_spot_id is not None
        scenic_name_str = (scenic_name or "").strip() if scenic_name else None
        if not use_id and not scenic_name_str:
            logger.warning("extract_and_store_entities: 缺少景区上下文(scenic_spot_id/scenic_name)，跳过图构建，避免离散节点")
            return

        # 先确保 ScenicSpot 存在
        if use_id:
            q_ensure_scenic = """
            MERGE (s:ScenicSpot {scenic_spot_id: $sid})
            ON CREATE SET s.name = coalesce($name, '景区')
            RETURN s
            """
            await self._execute_query_async(q_ensure_scenic, {
                "sid": int(scenic_spot_id),
                "name": scenic_name_str or "景区",
            })
        else:
            q_ensure_scenic_legacy = """
            MERGE (s:ScenicSpot {name: $name})
            RETURN s
            """
            await self._execute_query_async(q_ensure_scenic_legacy, {"name": scenic_name_str})

        # 创建文本节点，并立即连接到景区簇
        if use_id:
            q_text = """
            MERGE (t:Text {id: $text_id})
            SET t.content = $text
            WITH t
            MATCH (s:ScenicSpot {scenic_spot_id: $sid})
            MERGE (t)-[:DESCRIBES]->(s)
            RETURN t
            """
            await self._execute_query_async(q_text, {
                "text_id": text_id,
                "text": text,
                "sid": int(scenic_spot_id),
            })
        else:
            q_text_legacy = """
            MERGE (t:Text {id: $text_id})
            SET t.content = $text
            WITH t
            MATCH (s:ScenicSpot {name: $name})
            MERGE (t)-[:DESCRIBES]->(s)
            RETURN t
            """
            await self._execute_query_async(q_text_legacy, {
                "text_id": text_id,
                "text": text,
                "name": scenic_name_str,
            })

        # 创建实体节点并建立关系（Text -[:MENTIONS]-> Entity，Text 已连到 ScenicSpot）
        for entity in entities:
            entity_name = entity.get("text")
            if not entity_name:
                continue
            entity_type = entity.get("type", "KEYWORD")
            if entity_type not in ("LOCATION", "PERSON", "ORG", "OTHER", "KEYWORD", "ENTITY"):
                entity_type = "KEYWORD"
            create_entity_query = f"""
            MATCH (t:Text {{id: $text_id}})
            MERGE (e:{entity_type} {{name: $name}})
            MERGE (t)-[:MENTIONS]->(e)
            RETURN e
            """
            await self._execute_query_async(create_entity_query, {
                "text_id": text_id,
                "name": str(entity_name).strip(),
            })

    async def build_scenic_cluster(
        self,
        parsed: Dict[str, Any],
        text_id: str | None = None,
        scenic_spot_id: int | None = None,
        scenic_name_override: str | None = None,
        clear_existing: bool = False,
    ) -> None:
        """
        根据结构化的景区信息，在 Neo4j 中构建以景区为中心的一簇节点和关系。
        确保所有节点都连接到 ScenicSpot 中心节点，形成一簇。
        
        预期 parsed 结构：
        {
          "scenic_spot": "蜀南竹海旅游度假区",
          "location": ["四川省","宜宾市","长宁县"],
          "area": "10.2平方公里",
          "features": [...],
          "spots": [...],
          "awards": [...]
        }
        """
        scenic_name = scenic_name_override or parsed.get("scenic_spot")
        if not scenic_name:
            return
        scenic_name = str(scenic_name).strip()
        use_id = scenic_spot_id is not None
        if not use_id:
            for suffix in ["旅游度假区", "旅游区", "度假区", "风景区", "景区"]:
                if scenic_name.endswith(suffix) and len(scenic_name) > len(suffix):
                    scenic_name = scenic_name[:-len(suffix)]
                    break
            scenic_name = scenic_name.strip()
        sid = int(scenic_spot_id) if use_id else None
        
        logger.info(f"Building scenic cluster for '{scenic_name}' (text_id={text_id})")

        area = parsed.get("area")
        locations = parsed.get("location") or []
        features = parsed.get("features") or []
        spots = parsed.get("spots") or []
        awards = parsed.get("awards") or []
        # 新增：票务、开放时间、交通、服务设施等结构化字段（字符串），作为 ScenicSpot 的属性存储
        ticket_info = parsed.get("ticket_info")
        opening_hours = parsed.get("opening_hours")
        transport_info = parsed.get("transport_info")
        service_facilities = parsed.get("service_facilities")
        # clear_existing=False（默认）时，不会清空原有簇，只做增量合并；
        # 只有在“重建簇”类工具中才会传 True，触发清理逻辑。
        if clear_existing:
            if text_id:
                q_clean_text = """
                MATCH (t:Text {id: $text_id})
                OPTIONAL MATCH (t)-[r1:MENTIONS]->(e)
                DELETE r1
                WITH t
                OPTIONAL MATCH (t)-[r2:DESCRIBES]->(s:ScenicSpot)
                DELETE r2
                WITH t
                DETACH DELETE t
                """
                await self._execute_query_async(q_clean_text, {"text_id": text_id})
            q_clean_scenic_rels = """
            MATCH (s:ScenicSpot {scenic_spot_id: $sid})-[r:HAS_SPOT|HAS_FEATURE|HAS_HONOR|位于]->(n)
            DELETE r
            """
            if scenic_spot_id is not None:
                await self._execute_query_async(q_clean_scenic_rels, {"sid": int(scenic_spot_id)})
            else:
                q_clean_scenic_rels_legacy = """
                MATCH (s:ScenicSpot {name: $name})-[r:HAS_SPOT|HAS_FEATURE|HAS_HONOR|位于]->(n)
                DELETE r
                """
                await self._execute_query_async(q_clean_scenic_rels_legacy, {"name": scenic_name})
            q_clean_isolated = """
            MATCH (s:ScenicSpot {scenic_spot_id: $sid})-[r1:HAS_SPOT|HAS_FEATURE|HAS_HONOR]->(n)
            WHERE NOT (n)-[:位于|隶属]->() 
            WITH n, COUNT { (n)--() } AS connection_count
            WHERE connection_count <= 1
            DETACH DELETE n
            """
            if scenic_spot_id is not None:
                await self._execute_query_async(q_clean_isolated, {"sid": int(scenic_spot_id)})
            else:
                q_clean_isolated_legacy = """
                MATCH (s:ScenicSpot {name: $name})-[r1:HAS_SPOT|HAS_FEATURE|HAS_HONOR]->(n)
                WHERE NOT (n)-[:位于|隶属]->() 
                WITH n, COUNT { (n)--() } AS connection_count
                WHERE connection_count <= 1
                DETACH DELETE n
                """
                await self._execute_query_async(q_clean_isolated_legacy, {"name": scenic_name})
            q_clean_orphan_relations = """
            MATCH (s:ScenicSpot {scenic_spot_id: $sid})-[r]->(n)
            WHERE type(r) IN ['HAS_SPOT', 'HAS_FEATURE', 'HAS_HONOR']
            AND NOT EXISTS { (n)-[:位于|隶属]->() }
            AND COUNT { (n)--() } <= 1
            DELETE r
            """
            if scenic_spot_id is not None:
                await self._execute_query_async(q_clean_orphan_relations, {"sid": int(scenic_spot_id)})
            else:
                q_clean_orphan_relations_legacy = """
                MATCH (s:ScenicSpot {name: $name})-[r]->(n)
                WHERE type(r) IN ['HAS_SPOT', 'HAS_FEATURE', 'HAS_HONOR']
                AND NOT EXISTS { (n)-[:位于|隶属]->() }
                AND COUNT { (n)--() } <= 1
                DELETE r
                """
                await self._execute_query_async(q_clean_orphan_relations_legacy, {"name": scenic_name})
        location_str = "、".join(locations) if locations else None
        
        if use_id:
            q_scenic = """
            MERGE (s:ScenicSpot {scenic_spot_id: $sid})
            ON CREATE SET
                s.name = $name,
                s.area = $area,
                s.location = $location,
                s.ticket_info = $ticket_info,
                s.opening_hours = $opening_hours,
                s.transport_info = $transport_info,
                s.service_facilities = $service_facilities
            ON MATCH SET
                s.name = coalesce($name, s.name),
                s.area = coalesce(s.area, $area),
                s.location = coalesce(s.location, $location),
                s.ticket_info = coalesce(s.ticket_info, $ticket_info),
                s.opening_hours = coalesce(s.opening_hours, $opening_hours),
                s.transport_info = coalesce(s.transport_info, $transport_info),
                s.service_facilities = coalesce(s.service_facilities, $service_facilities)
            """
            await self._execute_query_async(
                q_scenic,
                {
                    "sid": sid,
                    "name": scenic_name,
                    "area": area,
                    "location": location_str,
                    "ticket_info": ticket_info,
                    "opening_hours": opening_hours,
                    "transport_info": transport_info,
                    "service_facilities": service_facilities,
                },
            )
        else:
            q_scenic_legacy = """
            MERGE (s:ScenicSpot {name: $name})
            ON CREATE SET
                s.area = $area,
                s.location = $location,
                s.ticket_info = $ticket_info,
                s.opening_hours = $opening_hours,
                s.transport_info = $transport_info,
                s.service_facilities = $service_facilities
            ON MATCH SET
                s.area = coalesce(s.area, $area),
                s.location = coalesce(s.location, $location),
                s.ticket_info = coalesce(s.ticket_info, $ticket_info),
                s.opening_hours = coalesce(s.opening_hours, $opening_hours),
                s.transport_info = coalesce(s.transport_info, $transport_info),
                s.service_facilities = coalesce(s.service_facilities, $service_facilities)
            """
            await self._execute_query_async(
                q_scenic_legacy,
                {
                    "name": scenic_name,
                    "area": area,
                    "location": location_str,
                    "ticket_info": ticket_info,
                    "opening_hours": opening_hours,
                    "transport_info": transport_info,
                    "service_facilities": service_facilities,
                },
            )
        if text_id:
            if use_id:
                q_txt = """
                MERGE (t:Text {id: $text_id})
                MERGE (s:ScenicSpot {scenic_spot_id: $sid})
                MERGE (t)-[:DESCRIBES]->(s)
                """
                await self._execute_query_async(q_txt, {"text_id": text_id, "sid": sid})
            else:
                q_txt_legacy = """
                MERGE (t:Text {id: $text_id})
                MERGE (s:ScenicSpot {name: $name})
                MERGE (t)-[:DESCRIBES]->(s)
                """
                await self._execute_query_async(q_txt_legacy, {"text_id": text_id, "name": scenic_name})
        if clear_existing:
            if use_id:
                q_clean_loc = """
                MATCH (s:ScenicSpot {scenic_spot_id: $sid})-[r:位于]->()
                DELETE r
                """
                await self._execute_query_async(q_clean_loc, {"sid": sid})
            else:
                q_clean_loc_legacy = """
                MATCH (s:ScenicSpot {name: $name})-[r:位于]->()
                DELETE r
                """
                await self._execute_query_async(q_clean_loc_legacy, {"name": scenic_name})
        if locations:
            params = {"s_name": scenic_name}
            if len(locations) >= 3:
                q_loc = """
                MERGE (prov:Province {name: $prov})
                MERGE (city:City {name: $city})
                MERGE (county:County {name: $county})
                MERGE (s:ScenicSpot {scenic_spot_id: $sid})
                MERGE (city)-[:隶属]->(prov)
                MERGE (county)-[:隶属]->(city)
                MERGE (s)-[:位于]->(county)
                """
                params.update({
                    "prov": locations[0],
                    "city": locations[1],
                    "county": locations[2]
                })
                if use_id:
                    params["sid"] = sid
                    await self._execute_query_async(q_loc, params)
                else:
                    q_loc_legacy = """
                    MERGE (prov:Province {name: $prov})
                    MERGE (city:City {name: $city})
                    MERGE (county:County {name: $county})
                    MERGE (s:ScenicSpot {name: $s_name})
                    MERGE (city)-[:隶属]->(prov)
                    MERGE (county)-[:隶属]->(city)
                    MERGE (s)-[:位于]->(county)
                    """
                    await self._execute_query_async(q_loc_legacy, params)
            elif len(locations) == 2:
                q_loc = """
                MERGE (prov:Province {name: $prov})
                MERGE (city:City {name: $city})
                MERGE (s:ScenicSpot {scenic_spot_id: $sid})
                MERGE (city)-[:隶属]->(prov)
                MERGE (s)-[:位于]->(city)
                """
                params.update({
                    "prov": locations[0],
                    "city": locations[1]
                })
                if use_id:
                    params["sid"] = sid
                    await self._execute_query_async(q_loc, params)
                else:
                    q_loc_legacy = """
                    MERGE (prov:Province {name: $prov})
                    MERGE (city:City {name: $city})
                    MERGE (s:ScenicSpot {name: $s_name})
                    MERGE (city)-[:隶属]->(prov)
                    MERGE (s)-[:位于]->(city)
                    """
                    await self._execute_query_async(q_loc_legacy, params)
            elif len(locations) == 1:
                q_loc = """
                MERGE (prov:Province {name: $prov})
                MERGE (s:ScenicSpot {scenic_spot_id: $sid})
                MERGE (s)-[:位于]->(prov)
                """
                params.update({"prov": locations[0]})
                if use_id:
                    params["sid"] = sid
                    await self._execute_query_async(q_loc, params)
                else:
                    q_loc_legacy = """
                    MERGE (prov:Province {name: $prov})
                    MERGE (s:ScenicSpot {name: $s_name})
                    MERGE (s)-[:位于]->(prov)
                    """
                    await self._execute_query_async(q_loc_legacy, params)
        spot_names = [str(x).strip() for x in (spots or []) if str(x).strip()]
        if spot_names:
            if use_id:
                q_spot = """
                UNWIND $names AS n
                MERGE (s:ScenicSpot {scenic_spot_id: $sid})
                MERGE (sp:Spot {name: n})
                MERGE (s)-[:HAS_SPOT]->(sp)
                """
                await self._execute_query_async(q_spot, {"names": spot_names, "sid": sid})
            else:
                q_spot_legacy = """
                UNWIND $names AS n
                MERGE (s:ScenicSpot {name: $s_name})
                MERGE (sp:Spot {name: n})
                MERGE (s)-[:HAS_SPOT]->(sp)
                """
                await self._execute_query_async(q_spot_legacy, {"names": spot_names, "s_name": scenic_name})
        feat_names = [str(x).strip() for x in (features or []) if str(x).strip()]
        if feat_names:
            if use_id:
                q_feat = """
                UNWIND $names AS n
                MERGE (s:ScenicSpot {scenic_spot_id: $sid})
                MERGE (f:Feature {name: n})
                MERGE (s)-[:HAS_FEATURE]->(f)
                """
                await self._execute_query_async(q_feat, {"names": feat_names, "sid": sid})
            else:
                q_feat_legacy = """
                UNWIND $names AS n
                MERGE (s:ScenicSpot {name: $s_name})
                MERGE (f:Feature {name: n})
                MERGE (s)-[:HAS_FEATURE]->(f)
                """
                await self._execute_query_async(q_feat_legacy, {"names": feat_names, "s_name": scenic_name})
        honor_names = [str(x).strip() for x in (awards or []) if str(x).strip()]
        if honor_names:
            if use_id:
                q_award = """
                UNWIND $names AS n
                MERGE (s:ScenicSpot {scenic_spot_id: $sid})
                MERGE (h:Honor {name: n})
                MERGE (s)-[:HAS_HONOR]->(h)
                """
                await self._execute_query_async(q_award, {"names": honor_names, "sid": sid})
            else:
                q_award_legacy = """
                UNWIND $names AS n
                MERGE (s:ScenicSpot {name: $s_name})
                MERGE (h:Honor {name: n})
                MERGE (s)-[:HAS_HONOR]->(h)
                """
                await self._execute_query_async(q_award_legacy, {"names": honor_names, "s_name": scenic_name})
        if use_id:
            q_verify = """
            MATCH (s:ScenicSpot {scenic_spot_id: $sid})
            OPTIONAL MATCH (s)-[r:HAS_SPOT|HAS_FEATURE|HAS_HONOR]->(n)
            RETURN COUNT(r) AS connected_count
            """
            result = await self._execute_query_async(q_verify, {"sid": sid})
        else:
            q_verify_legacy = """
            MATCH (s:ScenicSpot {name: $name})
            OPTIONAL MATCH (s)-[r:HAS_SPOT|HAS_FEATURE|HAS_HONOR]->(n)
            RETURN COUNT(r) AS connected_count
            """
            result = await self._execute_query_async(q_verify_legacy, {"name": scenic_name})
        if result and len(result) > 0:
            connected_count = result[0].get("connected_count", 0)
            logger.info(f"景区 '{scenic_name}' 已连接到 {connected_count} 个节点（Spot/Feature/Honor）")


graph_builder = GraphBuilder()

