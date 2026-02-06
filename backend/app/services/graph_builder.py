"""知识图谱构建：文本 -> Neo4j 图结构。"""
import logging
from typing import List, Dict, Any
from app.core.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)

class GraphBuilder:
    """将文本知识转为图结构并写入 Neo4j。"""

    def __init__(self):
        self.client = neo4j_client
    
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
            results = self.client.execute_query(query, attraction_data)
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
        self.client.execute_query(q_center, {
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
        self.client.execute_query(q_clean_rels, {"id": int(att_id)})
        q_clean_orphans = """
        MATCH (a:Attraction {id: $id})-[r:HAS_FEATURE|HAS_HONOR|HAS_IMAGE|HAS_AUDIO]->(n)
        WITH n, COUNT { (n)--() } AS c
        WHERE c <= 1
        DETACH DELETE n
        """
        self.client.execute_query(q_clean_orphans, {"id": int(att_id)})
        has_scenic_spot = False
        if scenic_spot_id:
            q_scenic_rel = """
            MATCH (a:Attraction {id: $id})
            MATCH (s:ScenicSpot {scenic_spot_id: $scenic_spot_id})
            MERGE (a)-[:属于]->(s)
            """
            self.client.execute_query(q_scenic_rel, {
                "id": int(att_id),
                "scenic_spot_id": int(scenic_spot_id)
            })
            has_scenic_spot = True
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
                self.client.execute_query(q_merge_spot, {
                    "id": int(att_id),
                    "scenic_spot_id": int(scenic_spot_id),
                    "name": name,
                })
            except Exception as e:
                logger.warning(f"合并景区子景点 Spot -> Attraction 失败: {e}")
        if text_id and text:
            q_text = """
            MERGE (t:Text {id: $text_id})
            SET t.content = $text
            WITH t
            MATCH (a:Attraction {id: $id})
            MERGE (t)-[:DESCRIBES]->(a)
            """
            self.client.execute_query(q_text, {"text_id": text_id, "text": text, "id": int(att_id)})
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
        self.client.execute_query(q_clean_loc, {"id": int(att_id)})
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
                self.client.execute_query(q_loc_nodes, params)
                q_loc_rel = """
                MATCH (a:Attraction {id: $id})
                MATCH (county:County {name: $county})
                MERGE (a)-[:位于]->(county)
                """
                self.client.execute_query(q_loc_rel, params)
            elif len(locations) == 2:
                q_loc_nodes = """
                MERGE (prov:Province {name: $prov})
                MERGE (city:City {name: $city})
                MERGE (city)-[:隶属]->(prov)
                """
                params.update({"prov": locations[0], "city": locations[1]})
                self.client.execute_query(q_loc_nodes, params)
                q_loc_rel = """
                MATCH (a:Attraction {id: $id})
                MATCH (city:City {name: $city})
                MERGE (a)-[:位于]->(city)
                """
                self.client.execute_query(q_loc_rel, params)
            elif len(locations) == 1:
                q_loc_nodes = """
                MERGE (prov:Province {name: $prov})
                """
                params.update({"prov": locations[0]})
                self.client.execute_query(q_loc_nodes, params)
                q_loc_rel = """
                MATCH (a:Attraction {id: $id})
                MATCH (prov:Province {name: $prov})
                MERGE (a)-[:位于]->(prov)
                """
                self.client.execute_query(q_loc_rel, params)
        category = (parsed.get("category") if parsed else None) or attraction_data.get("category")
        if category:
            q_cat = """
            MATCH (a:Attraction {id: $id})
            MERGE (c:Category {name: $name})
            MERGE (a)-[:HAS_CATEGORY]->(c)
            """
            self.client.execute_query(q_cat, {"id": int(att_id), "name": str(category).strip()})
        if attraction_data.get("image_url"):
            q_img = """
            MATCH (a:Attraction {id: $id})
            MERGE (img:Image {url: $url})
            MERGE (a)-[:HAS_IMAGE]->(img)
            """
            self.client.execute_query(q_img, {"id": int(att_id), "url": attraction_data.get("image_url")})
        if attraction_data.get("audio_url"):
            q_audio = """
            MATCH (a:Attraction {id: $id})
            MERGE (au:Audio {url: $url})
            MERGE (a)-[:HAS_AUDIO]->(au)
            """
            self.client.execute_query(q_audio, {"id": int(att_id), "url": attraction_data.get("audio_url")})
        features = (parsed.get("features") if parsed else None) or []
        honors = (parsed.get("honors") if parsed else None) or []
        if isinstance(features, list):
            feats = [str(x).strip() for x in features if str(x).strip()]
            if feats:
                q_f = """
                UNWIND $features AS fname
                MATCH (a:Attraction {id: $id})
                MERGE (f:Feature {name: fname})
                MERGE (a)-[:HAS_FEATURE]->(f)
                """
                self.client.execute_query(q_f, {"id": int(att_id), "features": feats})
        if isinstance(honors, list):
            hns = [str(x).strip() for x in honors if str(x).strip()]
            if hns:
                q_h = """
                UNWIND $honors AS hname
                MATCH (a:Attraction {id: $id})
                MERGE (h:Honor {name: hname})
                MERGE (a)-[:HAS_HONOR]->(h)
                """
                self.client.execute_query(q_h, {"id": int(att_id), "honors": hns})
    
    async def create_relationship(self, from_entity: str, to_entity: str, 
                                 relation_type: str, properties: Dict = None) -> bool:
        """创建实体之间的关系"""
        query = f"""
        MATCH (a), (b)
        WHERE a.name = $from_name AND b.name = $to_name
        MERGE (a)-[r:{relation_type}]->(b)
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
            results = self.client.execute_query(query, params)
            logger.info(f"Created relationship: {from_entity} -[{relation_type}]-> {to_entity}")
            return True
        except Exception as e:
            logger.error(f"Failed to create relationship: {e}")
            return False
    
    async def build_attraction_graph(self, attractions: List[Dict[str, Any]]):
        """批量构建景点图谱。"""
        for attraction in attractions:
            await self.create_attraction_node(attraction)
        for i, att1 in enumerate(attractions):
            for att2 in attractions[i+1:]:
                if att1.get('category') == att2.get('category'):
                    await self.create_relationship(
                        att1['name'],
                        att2['name'],
                        'NEARBY',
                        {'category': att1.get('category')}
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
            self.client.execute_query(q_ensure_scenic, {
                "sid": int(scenic_spot_id),
                "name": scenic_name_str or "景区",
            })
        else:
            q_ensure_scenic_legacy = """
            MERGE (s:ScenicSpot {name: $name})
            RETURN s
            """
            self.client.execute_query(q_ensure_scenic_legacy, {"name": scenic_name_str})

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
            self.client.execute_query(q_text, {
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
            self.client.execute_query(q_text_legacy, {
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
            self.client.execute_query(create_entity_query, {
                "text_id": text_id,
                "name": str(entity_name).strip(),
            })

    async def build_scenic_cluster(
        self,
        parsed: Dict[str, Any],
        text_id: str | None = None,
        scenic_spot_id: int | None = None,
        scenic_name_override: str | None = None,
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
            self.client.execute_query(q_clean_text, {"text_id": text_id})
        q_clean_scenic_rels = """
        MATCH (s:ScenicSpot {scenic_spot_id: $sid})-[r:HAS_SPOT|HAS_FEATURE|HAS_HONOR|位于]->(n)
        DELETE r
        """
        if scenic_spot_id is not None:
            self.client.execute_query(q_clean_scenic_rels, {"sid": int(scenic_spot_id)})
        else:
            q_clean_scenic_rels_legacy = """
            MATCH (s:ScenicSpot {name: $name})-[r:HAS_SPOT|HAS_FEATURE|HAS_HONOR|位于]->(n)
            DELETE r
            """
            self.client.execute_query(q_clean_scenic_rels_legacy, {"name": scenic_name})
        q_clean_isolated = """
        MATCH (s:ScenicSpot {scenic_spot_id: $sid})-[r1:HAS_SPOT|HAS_FEATURE|HAS_HONOR]->(n)
        WHERE NOT (n)-[:位于|隶属]->() 
        WITH n, COUNT { (n)--() } AS connection_count
        WHERE connection_count <= 1
        DETACH DELETE n
        """
        if scenic_spot_id is not None:
            self.client.execute_query(q_clean_isolated, {"sid": int(scenic_spot_id)})
        else:
            q_clean_isolated_legacy = """
            MATCH (s:ScenicSpot {name: $name})-[r1:HAS_SPOT|HAS_FEATURE|HAS_HONOR]->(n)
            WHERE NOT (n)-[:位于|隶属]->() 
            WITH n, COUNT { (n)--() } AS connection_count
            WHERE connection_count <= 1
            DETACH DELETE n
            """
            self.client.execute_query(q_clean_isolated_legacy, {"name": scenic_name})
        q_clean_orphan_relations = """
        MATCH (s:ScenicSpot {scenic_spot_id: $sid})-[r]->(n)
        WHERE type(r) IN ['HAS_SPOT', 'HAS_FEATURE', 'HAS_HONOR']
        AND NOT EXISTS { (n)-[:位于|隶属]->() }
        AND COUNT { (n)--() } <= 1
        DELETE r
        """
        if scenic_spot_id is not None:
            self.client.execute_query(q_clean_orphan_relations, {"sid": int(scenic_spot_id)})
        else:
            q_clean_orphan_relations_legacy = """
            MATCH (s:ScenicSpot {name: $name})-[r]->(n)
            WHERE type(r) IN ['HAS_SPOT', 'HAS_FEATURE', 'HAS_HONOR']
            AND NOT EXISTS { (n)-[:位于|隶属]->() }
            AND COUNT { (n)--() } <= 1
            DELETE r
            """
            self.client.execute_query(q_clean_orphan_relations_legacy, {"name": scenic_name})
        location_str = "、".join(locations) if locations else None
        
        if use_id:
            q_scenic = """
            MERGE (s:ScenicSpot {scenic_spot_id: $sid})
            ON CREATE SET
                s.name = $name,
                s.area = $area,
                s.location = $location
            ON MATCH SET
                s.name = coalesce($name, s.name),
                s.area = coalesce(s.area, $area),
                s.location = coalesce(s.location, $location)
            """
            self.client.execute_query(q_scenic, {"sid": sid, "name": scenic_name, "area": area, "location": location_str})
        else:
            q_scenic_legacy = """
            MERGE (s:ScenicSpot {name: $name})
            ON CREATE SET
                s.area = $area,
                s.location = $location
            ON MATCH SET
                s.area = coalesce(s.area, $area),
                s.location = coalesce(s.location, $location)
            """
            self.client.execute_query(q_scenic_legacy, {"name": scenic_name, "area": area, "location": location_str})
        if text_id:
            if use_id:
                q_txt = """
                MERGE (t:Text {id: $text_id})
                MERGE (s:ScenicSpot {scenic_spot_id: $sid})
                MERGE (t)-[:DESCRIBES]->(s)
                """
                self.client.execute_query(q_txt, {"text_id": text_id, "sid": sid})
            else:
                q_txt_legacy = """
                MERGE (t:Text {id: $text_id})
                MERGE (s:ScenicSpot {name: $name})
                MERGE (t)-[:DESCRIBES]->(s)
                """
                self.client.execute_query(q_txt_legacy, {"text_id": text_id, "name": scenic_name})
        if use_id:
            q_clean_loc = """
            MATCH (s:ScenicSpot {scenic_spot_id: $sid})-[r:位于]->()
            DELETE r
            """
            self.client.execute_query(q_clean_loc, {"sid": sid})
        else:
            q_clean_loc_legacy = """
            MATCH (s:ScenicSpot {name: $name})-[r:位于]->()
            DELETE r
            """
            self.client.execute_query(q_clean_loc_legacy, {"name": scenic_name})
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
                    self.client.execute_query(q_loc, params)
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
                    self.client.execute_query(q_loc_legacy, params)
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
                    self.client.execute_query(q_loc, params)
                else:
                    q_loc_legacy = """
                    MERGE (prov:Province {name: $prov})
                    MERGE (city:City {name: $city})
                    MERGE (s:ScenicSpot {name: $s_name})
                    MERGE (city)-[:隶属]->(prov)
                    MERGE (s)-[:位于]->(city)
                    """
                    self.client.execute_query(q_loc_legacy, params)
            elif len(locations) == 1:
                q_loc = """
                MERGE (prov:Province {name: $prov})
                MERGE (s:ScenicSpot {scenic_spot_id: $sid})
                MERGE (s)-[:位于]->(prov)
                """
                params.update({"prov": locations[0]})
                if use_id:
                    params["sid"] = sid
                    self.client.execute_query(q_loc, params)
                else:
                    q_loc_legacy = """
                    MERGE (prov:Province {name: $prov})
                    MERGE (s:ScenicSpot {name: $s_name})
                    MERGE (s)-[:位于]->(prov)
                    """
                    self.client.execute_query(q_loc_legacy, params)
        spot_names = [str(x).strip() for x in (spots or []) if str(x).strip()]
        if spot_names:
            if use_id:
                q_spot = """
                UNWIND $names AS n
                MERGE (s:ScenicSpot {scenic_spot_id: $sid})
                MERGE (sp:Spot {name: n})
                MERGE (s)-[:HAS_SPOT]->(sp)
                """
                self.client.execute_query(q_spot, {"names": spot_names, "sid": sid})
            else:
                q_spot_legacy = """
                UNWIND $names AS n
                MERGE (s:ScenicSpot {name: $s_name})
                MERGE (sp:Spot {name: n})
                MERGE (s)-[:HAS_SPOT]->(sp)
                """
                self.client.execute_query(q_spot_legacy, {"names": spot_names, "s_name": scenic_name})
        feat_names = [str(x).strip() for x in (features or []) if str(x).strip()]
        if feat_names:
            if use_id:
                q_feat = """
                UNWIND $names AS n
                MERGE (s:ScenicSpot {scenic_spot_id: $sid})
                MERGE (f:Feature {name: n})
                MERGE (s)-[:HAS_FEATURE]->(f)
                """
                self.client.execute_query(q_feat, {"names": feat_names, "sid": sid})
            else:
                q_feat_legacy = """
                UNWIND $names AS n
                MERGE (s:ScenicSpot {name: $s_name})
                MERGE (f:Feature {name: n})
                MERGE (s)-[:HAS_FEATURE]->(f)
                """
                self.client.execute_query(q_feat_legacy, {"names": feat_names, "s_name": scenic_name})
        honor_names = [str(x).strip() for x in (awards or []) if str(x).strip()]
        if honor_names:
            if use_id:
                q_award = """
                UNWIND $names AS n
                MERGE (s:ScenicSpot {scenic_spot_id: $sid})
                MERGE (h:Honor {name: n})
                MERGE (s)-[:HAS_HONOR]->(h)
                """
                self.client.execute_query(q_award, {"names": honor_names, "sid": sid})
            else:
                q_award_legacy = """
                UNWIND $names AS n
                MERGE (s:ScenicSpot {name: $s_name})
                MERGE (h:Honor {name: n})
                MERGE (s)-[:HAS_HONOR]->(h)
                """
                self.client.execute_query(q_award_legacy, {"names": honor_names, "s_name": scenic_name})
        if use_id:
            q_verify = """
            MATCH (s:ScenicSpot {scenic_spot_id: $sid})
            OPTIONAL MATCH (s)-[r:HAS_SPOT|HAS_FEATURE|HAS_HONOR]->(n)
            RETURN COUNT(r) AS connected_count
            """
            result = self.client.execute_query(q_verify, {"sid": sid})
        else:
            q_verify_legacy = """
            MATCH (s:ScenicSpot {name: $name})
            OPTIONAL MATCH (s)-[r:HAS_SPOT|HAS_FEATURE|HAS_HONOR]->(n)
            RETURN COUNT(r) AS connected_count
            """
            result = self.client.execute_query(q_verify_legacy, {"name": scenic_name})
        if result and len(result) > 0:
            connected_count = result[0].get("connected_count", 0)
            logger.info(f"景区 '{scenic_name}' 已连接到 {connected_count} 个节点（Spot/Feature/Honor）")


graph_builder = GraphBuilder()

