"""Neo4j 图数据库客户端"""
import logging
from neo4j import GraphDatabase
from app.core.config import settings

logger = logging.getLogger(__name__)

class Neo4jClient:
    def __init__(self):
        self.driver = None
        self._init_driver()

    def _init_driver(self):
        try:
            logger.info(f"正在连接 Neo4j: {settings.NEO4J_URI}")
            self.driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
            )
            with self.driver.session() as session:
                session.run("RETURN 1")
            logger.info("Neo4j 连接成功")
        except Exception as e:
            logger.error(f"Neo4j 连接失败: {e}")
            logger.warning(f"Neo4j URI: {settings.NEO4J_URI}, User: {settings.NEO4J_USER}")
            logger.warning("请确保 Neo4j 服务正在运行（docker-compose up -d neo4j）")
            self.driver = None

    def close(self):
        if self.driver:
            self.driver.close()

    def get_session(self):
        if not self.driver:
            raise Exception("Neo4j 未连接，请先启动 Neo4j 服务")
        return self.driver.session()

    def execute_query(self, query: str, parameters: dict = None):
        if not self.driver:
            logger.warning("Neo4j 未连接，返回空结果")
            return []
        try:
            with self.get_session() as session:
                result = session.run(query, parameters or {})
                return [record.data() for record in result]
        except Exception as e:
            logger.error(f"Neo4j 查询失败: {e}")
            raise

neo4j_client = Neo4jClient()

