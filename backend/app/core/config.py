"""
应用配置管理
"""
from pydantic import PostgresDsn
from pydantic_settings import BaseSettings
from typing import List, Optional
from urllib.parse import quote_plus

class Settings(BaseSettings):
    # 数据库配置 - 优先使用 DATABASE_URL（现代化方式，Prisma 使用）
    DATABASE_URL: Optional[PostgresDsn] = None
    
    # 备用配置（如果未提供 DATABASE_URL，则使用这些配置构建）
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
        # 如果未提供 DATABASE_URL，从单独配置构建
        encoded_password = quote_plus(self.POSTGRES_PASSWORD)
        url = f"postgresql://{self.POSTGRES_USER}:{encoded_password}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        return url
    
    # Neo4j 配置
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = ""
    
    # Milvus 配置
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    
    # Azure TTS 配置
    AZURE_SPEECH_KEY: str = ""
    AZURE_SPEECH_REGION: str = ""
    
    # OpenAI API（兼容硅基流动）
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: str = ""  # 硅基流动API地址，例如: https://api.siliconflow.cn/v1
    OPENAI_MODEL: str = "Pro/deepseek-ai/DeepSeek-R1"  # 默认模型，可配置为硅基流动支持的模型
    
    # JWT 配置
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    
    # CORS 配置
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"  # 确保 .env 文件以 UTF-8 编码读取
        case_sensitive = True

settings = Settings()

