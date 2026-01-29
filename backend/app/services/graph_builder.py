"""
知识图谱构建服务
用于将文本知识转换为图结构存储到 Neo4j
"""
import logging
from typing import List, Dict, Any
from app.core.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)

class GraphBuilder:
    """
    知识图谱构建器
    
    将文本知识转换为图结构：
    - 提取实体（景点、人物、事件等）
    - 识别关系（相邻、相关、推荐等）
    - 存储到 Neo4j 图数据库
    """
    
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
        """
        以“单个景点”为中心构建一簇（星状簇），确保不会产生离散节点。

        - 中心节点：(:Attraction {id})
        - 辐射节点：Category / Feature / Honor / Image / Audio / 位置链（省市县）
        - 关系：HAS_CATEGORY / HAS_FEATURE / HAS_HONOR / HAS_IMAGE / HAS_AUDIO / 位于 / 隶属
        """
        if not attraction_data:
            return
        att_id = attraction_data.get("id")
        if att_id is None:
            return
        name = attraction_data.get("name") or ""
        name = str(name).strip()
        if not name:
            return

        # 获取景区ID（景点所属的景区）
        scenic_spot_id = attraction_data.get("scenic_spot_id")

        # 1) upsert 中心节点
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

        # 2) 清理该景点旧簇关系（保留位置节点/类别节点/景区节点本体）
        q_clean_rels = """
        MATCH (a:Attraction {id: $id})-[r:HAS_CATEGORY|HAS_FEATURE|HAS_HONOR|HAS_IMAGE|HAS_AUDIO|位于|属于]->(n)
        DELETE r
        """
        self.client.execute_query(q_clean_rels, {"id": int(att_id)})

        # 3) 清理“只属于这个景点”的孤立辐射节点（Feature/Honor/Image/Audio）
        q_clean_orphans = """
        MATCH (a:Attraction {id: $id})-[r:HAS_FEATURE|HAS_HONOR|HAS_IMAGE|HAS_AUDIO]->(n)
        WITH n, COUNT { (n)--() } AS c
        WHERE c <= 1
        DETACH DELETE n
        """
        self.client.execute_query(q_clean_orphans, {"id": int(att_id)})

        # 4) Text 关联（可选）
        if text_id and text:
            q_text = """
            MERGE (t:Text {id: $text_id})
            SET t.content = $text
            WITH t
            MATCH (a:Attraction {id: $id})
            MERGE (t)-[:DESCRIBES]->(a)
            """
            self.client.execute_query(q_text, {"text_id": text_id, "text": text, "id": int(att_id)})

        # 5) 位置链（尽量从 parsed.location 取；否则从 attraction_data.location 做粗分）
        locations = []
        if parsed and isinstance(parsed.get("location"), list):
            locations = [str(x).strip() for x in parsed.get("location") if str(x).strip()]
        if not locations:
            loc_raw = attraction_data.get("location") or ""
            loc_raw = str(loc_raw)
            # 简单拆分：按常见分隔符
            for sep in [" ", "，", "、", ",", "/", "-", "—", "·"]:
                loc_raw = loc_raw.replace(sep, " ")
            parts = [p.strip() for p in loc_raw.split(" ") if p.strip()]
            # 过滤成“省/市/县/区”样式
            locations = [p for p in parts if any(p.endswith(s) for s in ["省", "市", "县", "区", "旗", "州"])]

        # 先删旧位置关系（避免重复）
        q_clean_loc = """
        MATCH (a:Attraction {id: $id})-[r:位于]->()
        DELETE r
        """
        self.client.execute_query(q_clean_loc, {"id": int(att_id)})

        if locations:
            params = {"id": int(att_id)}
            if len(locations) >= 3:
                # 先创建位置节点和层级关系
                q_loc_nodes = """
                MERGE (prov:Province {name: $prov})
                MERGE (city:City {name: $city})
                MERGE (county:County {name: $county})
                MERGE (city)-[:隶属]->(prov)
                MERGE (county)-[:隶属]->(city)
                """
                params.update({"prov": locations[0], "city": locations[1], "county": locations[2]})
                self.client.execute_query(q_loc_nodes, params)
                # 再建立景点与位置的关系
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

        # 6) Category（可选，允许共享）
        category = (parsed.get("category") if parsed else None) or attraction_data.get("category")
        if category:
            q_cat = """
            MATCH (a:Attraction {id: $id})
            MERGE (c:Category {name: $name})
            MERGE (a)-[:HAS_CATEGORY]->(c)
            """
            self.client.execute_query(q_cat, {"id": int(att_id), "name": str(category).strip()})

        # 7) Image/Audio（可选）
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

        # 8) Feature/Honor（来自 parsed）
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

        # 9) 关联到所属景区（ScenicSpot）- 区分景点和景区的关键关系
        if scenic_spot_id:
            # 先清理旧的景区关系
            q_clean_scenic = """
            MATCH (a:Attraction {id: $id})-[r:属于]->(:ScenicSpot)
            DELETE r
            """
            self.client.execute_query(q_clean_scenic, {"id": int(att_id)})
            
            # 建立景点与景区的关系
            q_scenic_rel = """
            MATCH (a:Attraction {id: $id})
            MATCH (s:ScenicSpot {scenic_spot_id: $scenic_spot_id})
            MERGE (a)-[:属于]->(s)
            """
            self.client.execute_query(q_scenic_rel, {
                "id": int(att_id),
                "scenic_spot_id": int(scenic_spot_id)
            })
            logger.info(f"景点 '{name}' (id={att_id}) 已关联到景区 (scenic_spot_id={scenic_spot_id})")
    
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
        """批量构建景点图谱"""
        # 创建所有景点节点
        for attraction in attractions:
            await self.create_attraction_node(attraction)
        
        # 基于地理位置创建"相邻"关系
        # 这里简化处理，实际应该计算距离
        for i, att1 in enumerate(attractions):
            for att2 in attractions[i+1:]:
                if att1.get('category') == att2.get('category'):
                    await self.create_relationship(
                        att1['name'],
                        att2['name'],
                        'NEARBY',
                        {'category': att1.get('category')}
                    )
    
    async def extract_and_store_entities(self, text: str, text_id: str, 
                                        entities: List[Dict[str, Any]]):
        """
        从文本中提取实体并存储到图数据库
        
        这是 GraphRAG 知识构建的核心功能
        """
        # 创建文本节点
        query = """
        MERGE (t:Text {id: $text_id})
        SET t.content = $text
        RETURN t
        """
        self.client.execute_query(query, {"text_id": text_id, "text": text})
        
        # 创建实体节点并建立关系
        for entity in entities:
            entity_name = entity.get("text")
            entity_type = entity.get("type", "ENTITY")
            
            # 创建实体节点
            create_entity_query = f"""
            MERGE (e:{entity_type} {{name: $name}})
            RETURN e
            """
            self.client.execute_query(create_entity_query, {"name": entity_name})
            
            # 创建文本-实体关系
            create_rel_query = """
            MATCH (t:Text {id: $text_id}), (e {name: $entity_name})
            MERGE (t)-[:MENTIONS]->(e)
            RETURN t, e
            """
            self.client.execute_query(create_rel_query, {
                "text_id": text_id,
                "entity_name": entity_name
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
        
        # 规范化景区名称：去除可能的尾缀，确保一致性
        # 例如："蜀南竹海旅游度假区" -> "蜀南竹海"
        scenic_name = str(scenic_name).strip()
        # 兼容旧数据：如果没给 scenic_spot_id（例如公共上传接口），保留原有“去尾缀”归一化
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

        # 先彻底清理该 text_id 和景区相关的所有旧数据，确保重建时形成一簇
        if text_id:
            # 1) 删除该 text_id 的 Text 节点及其所有关系（包括 MENTIONS 和 DESCRIBES）
            #    这会清理掉之前通过 extract_and_store_entities 创建的分散节点
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
        
        # 2) 无论是否有其他 Text 节点，都清理该 ScenicSpot 的所有关系
        #    这样可以确保每次重建时都形成一个完整的簇
        #    注意：位置节点（省/市/县）不会被删除，因为它们可能被其他景区共享
        q_clean_scenic_rels = """
        MATCH (s:ScenicSpot {scenic_spot_id: $sid})-[r:HAS_SPOT|HAS_FEATURE|HAS_HONOR|位于]->(n)
        DELETE r
        """
        if scenic_spot_id is not None:
            self.client.execute_query(q_clean_scenic_rels, {"sid": int(scenic_spot_id)})
        else:
            # 兼容旧逻辑：没有 id 时仍按 name 清理
            q_clean_scenic_rels_legacy = """
            MATCH (s:ScenicSpot {name: $name})-[r:HAS_SPOT|HAS_FEATURE|HAS_HONOR|位于]->(n)
            DELETE r
            """
            self.client.execute_query(q_clean_scenic_rels_legacy, {"name": scenic_name})
        
        # 3) 删除只连接到该景区的孤立节点（子景点、特色、荣誉等）
        #    确保这些节点不会成为离散节点
        #    注意：保留位置节点（省/市/县），因为它们可能被其他景区共享
        #    注意：如果一个节点连接到多个景区，不应该删除（但这种情况不应该发生，因为我们清理了所有关系）
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
        
        # 4) 额外检查：删除任何可能遗留的、只连接到该景区的关系
        #    确保没有离散的节点
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

        # 景区节点（MERGE 确保唯一）
        # 构建位置字符串（用于存储）
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

        # 可选：把文本节点跟景区挂在一起，形成 text -> scenic 的关联
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

        # 清理景区的位置关系（避免重复）
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

        # 位置层级：省 / 市 / 县（一次性构建完整层级链，确保连成一簇）
        if locations:
            params = {"s_name": scenic_name}
            # 构建完整的层级关系链，确保所有位置节点都连在一起
            if len(locations) >= 3:
                # 省 -> 市 -> 县 -> 景区
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
                # 省 -> 市 -> 景区
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
                # 省 -> 景区
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

        # 子景点（使用 Spot 节点，避免与真实 :Attraction{id} 冲突）
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

        # 特色（Feature）批量写入
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

        # 荣誉（Honor）批量写入
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
        
        # 最终验证：确保所有创建的节点都连接到 ScenicSpot，没有离散节点
        # 这个查询用于日志记录，帮助调试
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


# 全局图构建器实例
graph_builder = GraphBuilder()

