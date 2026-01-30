"""RAG / GraphRAG 相关的配置常量与默认参数。"""

from typing import Final
from app.core.config import settings

# 相似度阈值：低于此值视为不相关
RAG_RELEVANCE_SCORE_THRESHOLD: Final[float] = getattr(
    settings, "GRAPHRAG_RELEVANCE_THRESHOLD", 0.2
)

# 默认向量集合名称
RAG_COLLECTION_NAME: Final[str] = getattr(
    settings, "GRAPHRAG_COLLECTION_NAME", "tour_knowledge"
)

# 向量模型名称
RAG_EMBEDDING_MODEL_NAME: Final[str] = getattr(
    settings,
    "GRAPHRAG_EMBEDDING_MODEL",
    "paraphrase-multilingual-MiniLM-L12-v2",
)

# 检索 top_k 默认值
RAG_DEFAULT_TOP_K: Final[int] = int(getattr(settings, "GRAPHRAG_TOP_K", 5) or 5)

# 简单内存缓存上限，避免无限增长
EMBEDDING_CACHE_MAX_SIZE: Final[int] = 1024
VECTOR_SEARCH_CACHE_MAX_SIZE: Final[int] = 256

# 缓存 TTL（秒）
EMBEDDING_CACHE_TTL_SECONDS: Final[int] = int(
    getattr(settings, "GRAPHRAG_EMBEDDING_CACHE_TTL_SECONDS", 1800) or 1800
)
VECTOR_SEARCH_CACHE_TTL_SECONDS: Final[int] = int(
    getattr(settings, "GRAPHRAG_VECTOR_SEARCH_CACHE_TTL_SECONDS", 300) or 300
)

# 缓存统计日志频率（每 N 次调用输出一次）
CACHE_STATS_LOG_EVERY_N_CALLS: Final[int] = int(
    getattr(settings, "GRAPHRAG_CACHE_STATS_LOG_EVERY_N_CALLS", 200) or 200
)

# Milvus 检索参数
MILVUS_METRIC_TYPE: Final[str] = getattr(
    settings, "GRAPHRAG_MILVUS_METRIC_TYPE", "L2"
) or "L2"
MILVUS_NPROBE: Final[int] = int(
    getattr(settings, "GRAPHRAG_MILVUS_NPROBE", 10) or 10
)

