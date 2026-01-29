"""
Milvus 向量数据库客户端
"""
import logging
from app.core.config import settings

try:
    from pymilvus import connections, Collection, utility
    _MILVUS_AVAILABLE = True
except Exception as e:  # pragma: no cover
    # 允许在未安装/未启用 Milvus 的环境中继续启动服务（向量检索会降级为空结果）
    connections = None
    Collection = None
    utility = None
    _MILVUS_AVAILABLE = False
    _MILVUS_IMPORT_ERROR = e

logger = logging.getLogger(__name__)

class MilvusClient:
    def __init__(self):
        self.connected = False
        # 懒连接：不在 import/启动阶段连接，避免 Milvus 未启动时刷屏报错。
        # 需要向量检索时（如 RAGService.vector_search）再显式 connect()
    
    def connect(self):
        """连接到 Milvus"""
        if not _MILVUS_AVAILABLE:
            logger.warning(f"pymilvus not available, Milvus disabled: {_MILVUS_IMPORT_ERROR}")
            self.connected = False
            return
        try:
            connections.connect(
                alias="default",
                host=settings.MILVUS_HOST,
                port=settings.MILVUS_PORT
            )
            self.connected = True
            logger.info("Connected to Milvus")
        except Exception as e:
            logger.error(f"Failed to connect to Milvus: {e}")
            self.connected = False
    
    def disconnect(self):
        """断开连接"""
        if _MILVUS_AVAILABLE and self.connected:
            connections.disconnect("default")
            self.connected = False
    
    def get_collection(self, collection_name: str, load: bool = False):
        """获取集合
        
        Args:
            collection_name: 集合名称
            load: 是否自动加载集合到内存（用于搜索操作）
        """
        if not self.connected:
            self.connect()
        if not _MILVUS_AVAILABLE or not self.connected:
            raise RuntimeError("Milvus is not available/connected")
        collection = Collection(collection_name)
        if load:
            try:
                collection.load()
            except Exception as e:
                logger.warning(f"Failed to load collection '{collection_name}': {e}")
        return collection
    
    def create_collection_if_not_exists(self, collection_name: str, dimension: int = 384, load: bool = False):
        """创建集合（如果不存在）
        
        Args:
            collection_name: 集合名称
            dimension: 向量维度
            load: 是否自动加载集合到内存（用于搜索操作）
        """
        if not self.connected:
            self.connect()
        if not _MILVUS_AVAILABLE or not self.connected:
            raise RuntimeError("Milvus is not available/connected")
        
        if utility.has_collection(collection_name):
            collection = Collection(collection_name)
            if load:
                try:
                    collection.load()
                except Exception as e:
                    logger.warning(f"Failed to load existing collection '{collection_name}': {e}")
            return collection
        
        # 定义集合结构
        from pymilvus import FieldSchema, CollectionSchema, DataType
        
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="text_id", dtype=DataType.VARCHAR, max_length=200),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dimension),
        ]
        schema = CollectionSchema(fields, "Tour guide knowledge base")
        collection = Collection(collection_name, schema)
        
        # 创建索引
        index_params = {
            "metric_type": "L2",
            "index_type": "IVF_FLAT",
            "params": {"nlist": 1024}
        }
        collection.create_index("embedding", index_params)
        
        if load:
            try:
                collection.load()
            except Exception as e:
                logger.warning(f"Failed to load newly created collection '{collection_name}': {e}")
        
        return collection

# 全局 Milvus 客户端实例
milvus_client = MilvusClient()

