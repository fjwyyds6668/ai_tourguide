"""
应用配置管理
"""
import os
import json
from pydantic import PostgresDsn
from pydantic_settings import BaseSettings
from typing import List, Optional, Dict
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
    NEO4J_URI: str = "bolt://localhost:30001"  # Docker 映射端口（30000-40000范围）
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "12345678"  # 与 docker-compose.yml 中的密码一致
    
    # Milvus 配置
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 30002  # Docker 映射端口（30000-40000范围）
    
    # OpenAI API（兼容硅基流动）
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: str = ""  # 硅基流动API地址，例如: https://api.siliconflow.cn/v1
    OPENAI_MODEL: str = "Pro/deepseek-ai/DeepSeek-R1"  # 默认模型，可配置为硅基流动支持的模型
    
    # JWT 配置
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    
    # CORS 配置
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]
    
    # GraphRAG 自动更新配置
    AUTO_UPDATE_GRAPH_RAG: bool = True  # 是否在创建/更新景点/知识时自动更新 GraphRAG
    GRAPHRAG_COLLECTION_NAME: str = "tour_knowledge"  # GraphRAG 集合名称

    # ===== 离线 TTS（方案A：本地 PaddleSpeech）=====
    # 开关：启用后，Edge TTS 失败（403/网络）会自动降级到本地 TTS
    LOCAL_TTS_ENABLED: bool = False
    # 若为 True，则强制始终使用本地 TTS（不走 Edge）
    LOCAL_TTS_FORCE: bool = False
    # 本地 TTS 引擎选择：paddlespeech 或 coqui
    LOCAL_TTS_ENGINE: str = "paddlespeech"  # paddlespeech 或 coqui
    
    # PaddleSpeech 配置
    # PaddleSpeech 运行方式（建议用当前虚拟环境 python）。
    # 留空则自动使用当前进程的 sys.executable，避免误用系统/基础 python。
    # Windows 如需指定可填：E:\\Anaconda\\envs\\ai_tourguide\\python.exe
    PADDLESPEECH_PYTHON: str = ""
    # PaddleSpeech TTS 默认 voice key（在 PADDLESPEECH_VOICES_JSON 中配置）
    PADDLESPEECH_DEFAULT_VOICE: str = "fastspeech2_csmsc"
    # 多音色映射（JSON 字符串）：
    # {
    #   "fastspeech2_csmsc": {"am":"fastspeech2_csmsc","voc":"pwgan_csmsc"},
    #   "fastspeech2_male": {"am":"fastspeech2_csmsc","voc":"pwgan_csmsc","speaker":"male"}
    # }
    PADDLESPEECH_VOICES_JSON: str = "{}"

    # Coqui TTS 配置
    # Coqui TTS 模型名称（从 https://github.com/coqui-ai/TTS 选择）
    # 中文推荐：tts_models/zh-CN/baker/tacotron2-DDC-GST
    # 英文推荐：tts_models/en/ljspeech/tacotron2-DDC
    COQUI_TTS_MODEL: str = "tts_models/zh-CN/baker/tacotron2-DDC-GST"
    # Coqui TTS 默认说话人（speaker，某些模型支持多说话人）
    COQUI_TTS_SPEAKER: Optional[str] = None
    # Coqui TTS 语言（自动从模型推断，通常不需要设置）
    COQUI_TTS_LANG: Optional[str] = None

    @property
    def paddlespeech_voices(self) -> Dict[str, dict]:
        """解析 PaddleSpeech 多音色映射。"""
        try:
            data = json.loads(self.PADDLESPEECH_VOICES_JSON or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"  # 确保 .env 文件以 UTF-8 编码读取
        case_sensitive = True
        extra = "ignore"  # 忽略 .env 中未定义的字段（如 PYTHONIOENCODING, PYTHONUTF8）

settings = Settings()

