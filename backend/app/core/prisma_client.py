"""Prisma 客户端管理（单例）"""
import os
from prisma import Prisma
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from app.core.config import settings

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = settings.database_url

_prisma: Optional[Prisma] = None

async def get_prisma() -> Prisma:
    global _prisma
    if _prisma is None:
        if not os.environ.get('DATABASE_URL'):
            os.environ['DATABASE_URL'] = settings.database_url
        _prisma = Prisma()
        await _prisma.connect()
    return _prisma

async def disconnect_prisma():
    global _prisma
    if _prisma is not None:
        await _prisma.disconnect()
        _prisma = None

@asynccontextmanager
async def prisma_context() -> AsyncGenerator[Prisma, None]:
    prisma = await get_prisma()
    try:
        yield prisma
    finally:
        pass  # 单例模式不断开连接

