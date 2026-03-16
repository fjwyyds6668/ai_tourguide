"""景区 AI 数字人导游系统 - FastAPI 主入口"""
import os
import warnings

# 清除系统代理环境变量，确保所有外部请求直连，不受 VPN/代理软件影响
for _proxy_key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_proxy_key, None)

# 必须在其他模块导入前配置：抑制第三方库的已知警告
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

# 必须在 Python 启动时设置，对 Prisma 生成器也有效
if not os.environ.get('PYTHONIOENCODING'):
    os.environ['PYTHONIOENCODING'] = 'utf-8'
if not os.environ.get('PYTHONUTF8'):
    os.environ['PYTHONUTF8'] = '1'

from app.core.config import settings
from app.api import router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """启动时开启会话清理后台任务，关闭时取消。"""
    from app.services.session_service import session_service

    async def _cleanup_loop() -> None:
        while True:
            try:
                await asyncio.sleep(600)  # 每 10 分钟清理一次过期的内存会话
                session_service.cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                _logger.warning("Session cleanup error: %s", e)

    task = asyncio.create_task(_cleanup_loop())
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
# GZip 压缩，减少 JSON/文本传输体积
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

