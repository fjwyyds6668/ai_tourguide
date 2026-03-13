"""RAG / GraphRAG 相关的配置常量与默认参数。"""

from typing import Final
from app.core.config import settings

RAG_RELEVANCE_SCORE_THRESHOLD: Final[float] = getattr(
    settings, "GRAPHRAG_RELEVANCE_THRESHOLD", 0.2
)

RAG_COLLECTION_NAME: Final[str] = getattr(
    settings, "GRAPHRAG_COLLECTION_NAME", "tour_knowledge"
)

RAG_EMBEDDING_MODEL_NAME: Final[str] = getattr(
    settings,
    "GRAPHRAG_EMBEDDING_MODEL",
    "paraphrase-multilingual-MiniLM-L12-v2",
)

RAG_DEFAULT_TOP_K: Final[int] = int(getattr(settings, "GRAPHRAG_TOP_K", 5) or 5)

# 内存缓存上限，避免无限增长
EMBEDDING_CACHE_MAX_SIZE: Final[int] = 1024
VECTOR_SEARCH_CACHE_MAX_SIZE: Final[int] = 256

EMBEDDING_CACHE_TTL_SECONDS: Final[int] = int(
    getattr(settings, "GRAPHRAG_EMBEDDING_CACHE_TTL_SECONDS", 1800) or 1800
)
VECTOR_SEARCH_CACHE_TTL_SECONDS: Final[int] = int(
    getattr(settings, "GRAPHRAG_VECTOR_SEARCH_CACHE_TTL_SECONDS", 300) or 300
)

CACHE_STATS_LOG_EVERY_N_CALLS: Final[int] = int(
    getattr(settings, "GRAPHRAG_CACHE_STATS_LOG_EVERY_N_CALLS", 200) or 200
)

MILVUS_METRIC_TYPE: Final[str] = getattr(
    settings, "GRAPHRAG_MILVUS_METRIC_TYPE", "L2"
) or "L2"
MILVUS_NPROBE: Final[int] = int(
    getattr(settings, "GRAPHRAG_MILVUS_NPROBE", 10) or 10
)

