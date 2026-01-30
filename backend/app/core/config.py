"""应用配置（环境变量 + .env）。"""
import os
from pydantic import PostgresDsn
from pydantic_settings import BaseSettings
from typing import List, Optional
from urllib.parse import quote_plus

if not os.environ.get('PYTHONIOENCODING'):
    os.environ['PYTHONIOENCODING'] = 'utf-8'
if not os.environ.get('PYTHONUTF8'):
    os.environ['PYTHONUTF8'] = '1'

class Settings(BaseSettings):
    DATABASE_URL: Optional[PostgresDsn] = None
    
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "ai_tourguide"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""
    
    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return str(self.DATABASE_URL)
        encoded_password = quote_plus(self.POSTGRES_PASSWORD)
        url = f"postgresql://{self.POSTGRES_USER}:{encoded_password}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        return url
    NEO4J_URI: str = "bolt://localhost:30001"
    NEO4J_USER: str = "neo4j"
    # 出于安全考虑，默认密码留空，必须通过环境变量或 .env 显式配置
    NEO4J_PASSWORD: str = ""
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 30002
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: str = ""
    OPENAI_MODEL: str = "Pro/deepseek-ai/DeepSeek-R1"
    XFYUN_APPID: str = ""
    XFYUN_API_KEY: str = ""
    XFYUN_API_SECRET: str = ""
    XFYUN_VOICE: str = "x4_yezi"
    # JWT 密钥：生产环境必须通过环境变量设置，默认值仅供本地开发调试使用
    SECRET_KEY: str = "dev-change-me"
    ALGORITHM: str = "HS256"
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]
    AUTO_UPDATE_GRAPH_RAG: bool = True
    # GraphRAG / 检索相关配置
    GRAPHRAG_COLLECTION_NAME: str = "tour_knowledge"
    GRAPHRAG_EMBEDDING_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"
    GRAPHRAG_TOP_K: int = 5
    GRAPHRAG_RELEVANCE_THRESHOLD: float = 0.2
    GRAPHRAG_MILVUS_METRIC_TYPE: str = "L2"
    GRAPHRAG_MILVUS_NPROBE: int = 10
    # 缓存与可观测性
    GRAPHRAG_EMBEDDING_CACHE_TTL_SECONDS: int = 1800
    GRAPHRAG_VECTOR_SEARCH_CACHE_TTL_SECONDS: int = 300
    GRAPHRAG_CACHE_STATS_LOG_EVERY_N_CALLS: int = 200
    LOCAL_TTS_ENABLED: bool = False
    LOCAL_TTS_FORCE: bool = False
    LOCAL_TTS_ENGINE: str = "cosyvoice2"
    COSYVOICE2_MODEL_PATH: str = ""
    COSYVOICE2_DEVICE: str = "cpu"
    COSYVOICE2_LANGUAGE: str = "zh"
    COSYVOICE2_SPEAKER: Optional[str] = None
    COSYVOICE_PROMPT_WAV: str = ""
    COSYVOICE_PROMPT_TEXT: str = ""

    # 管理端 / 上传等配置
    ADMIN_MAX_IMAGE_SIZE_MB: int = 10
    ADMIN_ALLOWED_IMAGE_EXTS: List[str] = [".png", ".jpg", ".jpeg", ".webp", ".gif"]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"

settings = Settings()

