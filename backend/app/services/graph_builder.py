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

    async def build_scenic_cluster(self, parsed: Dict[str, Any], text_id: str | None = None) -> None:
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
        scenic_name = parsed.get("scenic_spot")
        if not scenic_name:
            return

        area = parsed.get("area")
        locations = parsed.get("location") or []
        features = parsed.get("features") or []
        spots = parsed.get("spots") or []
        awards = parsed.get("awards") or []

        # 先清理该景区相关的所有旧数据（包括孤立节点），确保重建时形成一簇
        # 1) 删除该景区的所有关系
        q_clean_all = """
        MATCH (s:ScenicSpot {name: $name})-[r]->()
        DELETE r
        """
        self.client.execute_query(q_clean_all, {"name": scenic_name})
        
        # 2) 删除只连接到该景区的孤立节点（避免散点残留）
        # 注意：保留可能被其他景区共享的位置节点（省/市/县）
        q_clean_isolated = """
        MATCH (s:ScenicSpot {name: $name})-[r1:拥有|特色|荣誉]->(n)
        WHERE NOT (n)-[:位于|隶属]->() AND COUNT { (n)--() } <= 1
        DETACH DELETE n
        """
        self.client.execute_query(q_clean_isolated, {"name": scenic_name})

        # 景区节点（MERGE 确保唯一）
        q_scenic = """
        MERGE (s:ScenicSpot {name: $name})
        ON CREATE SET s.area = $area
        ON MATCH SET s.area = coalesce(s.area, $area)
        """
        self.client.execute_query(q_scenic, {"name": scenic_name, "area": area})

        # 可选：把文本节点跟景区挂在一起，形成 text -> scenic 的关联
        if text_id:
            q_txt = """
            MERGE (t:Text {id: $text_id})
            MERGE (s:ScenicSpot {name: $name})
            MERGE (t)-[:DESCRIBES]->(s)
            """
            self.client.execute_query(q_txt, {"text_id": text_id, "name": scenic_name})

        # 清理景区的位置关系（避免重复）
        q_clean_loc = """
        MATCH (s:ScenicSpot {name: $name})-[r:位于]->()
        DELETE r
        """
        self.client.execute_query(q_clean_loc, {"name": scenic_name})

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
                MERGE (s:ScenicSpot {name: $s_name})
                MERGE (city)-[:隶属]->(prov)
                MERGE (county)-[:隶属]->(city)
                MERGE (s)-[:位于]->(county)
                """
                params.update({
                    "prov": locations[0],
                    "city": locations[1],
                    "county": locations[2]
                })
                self.client.execute_query(q_loc, params)
            elif len(locations) == 2:
                # 省 -> 市 -> 景区
                q_loc = """
                MERGE (prov:Province {name: $prov})
                MERGE (city:City {name: $city})
                MERGE (s:ScenicSpot {name: $s_name})
                MERGE (city)-[:隶属]->(prov)
                MERGE (s)-[:位于]->(city)
                """
                params.update({
                    "prov": locations[0],
                    "city": locations[1]
                })
                self.client.execute_query(q_loc, params)
            elif len(locations) == 1:
                # 省 -> 景区
                q_loc = """
                MERGE (prov:Province {name: $prov})
                MERGE (s:ScenicSpot {name: $s_name})
                MERGE (s)-[:位于]->(prov)
                """
                params.update({"prov": locations[0]})
                self.client.execute_query(q_loc, params)

        # 子景点
        for name in spots:
            q_spot = """
            MERGE (sub:Spot {name:$name})
            MERGE (s:ScenicSpot {name:$s_name})-[:拥有]->(sub)
            """
            self.client.execute_query(q_spot, {"name": name, "s_name": scenic_name})

        # 特色
        for name in features:
            q_feat = """
            MERGE (f:Feature {name:$name})
            MERGE (s:ScenicSpot {name:$s_name})-[:特色]->(f)
            """
            self.client.execute_query(q_feat, {"name": name, "s_name": scenic_name})

        # 荣誉
        for name in awards:
            q_award = """
            MERGE (a:Award {name:$name})
            MERGE (s:ScenicSpot {name:$s_name})-[:荣誉]->(a)
            """
            self.client.execute_query(q_award, {"name": name, "s_name": scenic_name})


# 全局图构建器实例
graph_builder = GraphBuilder()

