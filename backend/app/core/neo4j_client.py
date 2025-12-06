"""
Neo4j 图数据库客户端
"""
from neo4j import GraphDatabase
from app.core.config import settings

class Neo4jClient:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
    
    def close(self):
        self.driver.close()
    
    def get_session(self):
        return self.driver.session()
    
    def execute_query(self, query: str, parameters: dict = None):
        """执行 Cypher 查询"""
        with self.get_session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

# 全局 Neo4j 客户端实例
neo4j_client = Neo4jClient()

