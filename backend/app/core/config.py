"""
应用配置管理
"""
import os
from pydantic import PostgresDsn
from pydantic_settings import BaseSettings
from typing import List, Optional
from urllib.parse import quote_plus

# 在加载配置之前设置编码环境变量
# 这些变量对 Prisma 生成器和应用运行都重要
# 如果 .env 中有这些变量，会在 Settings 加载时自动读取
# 但为了确保在 Prisma 生成时也生效，我们在这里设置默认值
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
        """获取数据库连接 URL（Prisma 使用）"""
        if self.DATABASE_URL:
            return str(self.DATABASE_URL)
        encoded_password = quote_plus(self.POSTGRES_PASSWORD)
        url = f"postgresql://{self.POSTGRES_USER}:{encoded_password}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        return url
    
    # Neo4j 配置
    NEO4J_URI: str = "bolt://localhost:30001"  # Docker 映射端口（30000-40000范围）
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "12345678"  # 与 docker-compose.yml 中的密码一致
    
    # Milvus 配置
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 30002  # Docker 映射端口（30000-40000范围）
    
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: str = ""
    OPENAI_MODEL: str = "Pro/deepseek-ai/DeepSeek-R1"
    
    # JWT 配置
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    
    # CORS 配置
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]
    
    # GraphRAG 自动更新配置
    AUTO_UPDATE_GRAPH_RAG: bool = True  # 是否在创建/更新景点/知识时自动更新 GraphRAG
    GRAPHRAG_COLLECTION_NAME: str = "tour_knowledge"  # GraphRAG 集合名称

    # ===== 离线 TTS（备用方案：本地 TTS）=====
    # 开关：启用后，Edge TTS 失败（403/网络）会自动降级到本地 TTS
    LOCAL_TTS_ENABLED: bool = False
    # 若为 True，则强制始终使用本地 TTS（不走 Edge）
    LOCAL_TTS_FORCE: bool = False
    # 本地 TTS 引擎选择：bertvits2 或 cosyvoice2
    LOCAL_TTS_ENGINE: str = "cosyvoice2"  # 默认使用 CosyVoice2
    
    # Bert-VITS2 配置
    # Bert-VITS2 配置文件路径（config.json）
    BERTVITS2_CONFIG_PATH: str = ""
    # Bert-VITS2 模型文件路径（.pth）
    BERTVITS2_MODEL_PATH: str = ""
    # Bert-VITS2 设备（cpu/cuda）
    BERTVITS2_DEVICE: str = "cpu"
    # Bert-VITS2 默认说话人（从模型配置中获取，如果未设置则使用第一个可用说话人）
    BERTVITS2_DEFAULT_SPEAKER: Optional[str] = None
    # Bert-VITS2 语言（仅支持中文 ZH）
    BERTVITS2_LANGUAGE: str = "ZH"
    # Bert-VITS2 合成参数
    BERTVITS2_SDP_RATIO: float = 0.5
    BERTVITS2_NOISE_SCALE: float = 0.6
    BERTVITS2_NOISE_SCALE_W: float = 0.8
    BERTVITS2_LENGTH_SCALE: float = 1.0
    
    # CosyVoice2 配置
    # CosyVoice2 模型路径（可选，如果为空则从 ModelScope/HuggingFace 自动下载）
    COSYVOICE2_MODEL_PATH: str = ""
    # CosyVoice2 设备（cpu/cuda）
    COSYVOICE2_DEVICE: str = "cpu"
    # CosyVoice2 语言（zh/en/ja 等）
    COSYVOICE2_LANGUAGE: str = "zh"
    # CosyVoice2 说话人（可选）
    COSYVOICE2_SPEAKER: Optional[str] = None
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"

settings = Settings()

