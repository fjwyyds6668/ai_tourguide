"""景区 AI 数字人导游系统 - FastAPI 主入口"""
import os
import warnings

for _proxy_key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_proxy_key, None)

warnings.filterwarnings("ignore", category=UserWarning, module="jieba._compat")
warnings.filterwarnings("ignore", category=FutureWarning, module="huggingface_hub.file_download")
warnings.filterwarnings("ignore", message=".*resume_download is deprecated.*")

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

_logger = logging.getLogger(__name__)

if not os.environ.get('PYTHONIOENCODING'):
    os.environ['PYTHONIOENCODING'] = 'utf-8'
if not os.environ.get('PYTHONUTF8'):
    os.environ['PYTHONUTF8'] = '1'

from app.core.config import settings
from app.api import router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """启动时建表、开启会话清理后台任务，关闭时取消。"""
    try:
        from app.core.database import engine, Base
        from app.models import Attraction, User, Interaction  # noqa: F401 — 注册模型
        Base.metadata.create_all(bind=engine)
        _logger.info("Database tables ensured.")
    except Exception as _e:
        _logger.error("Failed to create database tables: %s", _e)

    from app.services.session_service import session_service

    async def _cleanup_loop() -> None:
        while True:
            try:
                await asyncio.sleep(600)
                session_service.cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                _logger.warning("Session cleanup error: %s", e)

    async def _warmup_all() -> None:
        """预热 Embedding / Milvus / Neo4j / LLM，消除第一次问答的冷启动延迟。"""
        await asyncio.sleep(0.5)
        loop = asyncio.get_running_loop()
        from app.services.rag_service import rag_service

        try:
            await loop.run_in_executor(None, lambda: rag_service.generate_embedding("预热"))
            _logger.info("Embedding model warmed up")
        except Exception as e:
            _logger.warning("Embedding warmup failed: %s", e)

        try:
            await rag_service.vector_search("预热", top_k=1)
            _logger.info("Milvus warmed up")
        except Exception as e:
            _logger.warning("Milvus warmup failed: %s", e)

        try:
            await loop.run_in_executor(None, lambda: rag_service.graph_search.__func__ and None)
            from app.core.neo4j_client import neo4j_client
            await loop.run_in_executor(
                None,
                lambda: neo4j_client.execute_query("RETURN 1 AS ping", {}),
            )
            _logger.info("Neo4j warmed up")
        except Exception as e:
            _logger.warning("Neo4j warmup failed: %s", e)

        try:
            if rag_service.llm_client is not None:
                await loop.run_in_executor(
                    None,
                    lambda: rag_service.llm_client.chat.completions.create(
                        model=settings.OPENAI_MODEL,
                        messages=[{"role": "user", "content": "hi"}],
                        max_tokens=1,
                    ),
                )
                _logger.info("LLM connection warmed up")
        except Exception as e:
            _logger.warning("LLM warmup failed: %s", e)

    task = asyncio.create_task(_cleanup_loop())
    asyncio.create_task(_warmup_all())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="AI 数字人导游系统 API",
    description="景区智能导览系统后端 API",
    version="1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=500)

app.include_router(router, prefix="/api/v1")

_uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(_uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_uploads_dir), name="uploads")


@app.get("/")
async def root():
    return {"message": "AI 数字人导游系统 API", "version": "1.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=18000)

