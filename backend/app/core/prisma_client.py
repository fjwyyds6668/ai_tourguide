"""
Prisma 客户端管理
"""
import os
from prisma import Prisma
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from app.core.config import settings

# 确保 DATABASE_URL 环境变量已设置（Prisma 需要）
if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = settings.database_url

# 全局 Prisma 客户端实例
_prisma: Optional[Prisma] = None

async def get_prisma() -> Prisma:
    """获取 Prisma 客户端实例（单例模式）"""
    global _prisma
    if _prisma is None:
        # 确保 DATABASE_URL 已设置
        if not os.environ.get('DATABASE_URL'):
            os.environ['DATABASE_URL'] = settings.database_url
        _prisma = Prisma()
        await _prisma.connect()
    return _prisma

async def disconnect_prisma():
    """断开 Prisma 连接"""
    global _prisma
    if _prisma is not None:
        await _prisma.disconnect()
        _prisma = None

@asynccontextmanager
async def prisma_context() -> AsyncGenerator[Prisma, None]:
    """Prisma 客户端上下文管理器"""
    prisma = await get_prisma()
    try:
        yield prisma
    finally:
        # 注意：这里不断开连接，因为使用的是单例模式
        pass

