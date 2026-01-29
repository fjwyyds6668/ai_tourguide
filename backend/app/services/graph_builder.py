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

        # 景区节点
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

        # 位置层级：省 / 市 / 县
        if locations:
            params = {"s_name": scenic_name}
            cypher_parts = []
            if len(locations) >= 1:
                params["prov"] = locations[0]
                cypher_parts.append("MERGE (prov:Province {name:$prov})")
            if len(locations) >= 2:
                params["city"] = locations[1]
                cypher_parts.append("MERGE (city:City {name:$city})")
            if len(locations) >= 3:
                params["county"] = locations[2]
                cypher_parts.append("MERGE (county:County {name:$county})")
            if len(locations) >= 2:
                cypher_parts.append("MERGE (city)-[:隶属]->(prov)")
            if len(locations) >= 3:
                cypher_parts.append("MERGE (county)-[:隶属]->(city)")
                cypher_parts.append("MERGE (s:ScenicSpot {name:$s_name})-[:位于]->(county)")
            elif len(locations) == 2:
                cypher_parts.append("MERGE (s:ScenicSpot {name:$s_name})-[:位于]->(city)")
            elif len(locations) == 1:
                cypher_parts.append("MERGE (s:ScenicSpot {name:$s_name})-[:位于]->(prov)")

            q_loc = "\n".join(cypher_parts)
            if q_loc:
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

