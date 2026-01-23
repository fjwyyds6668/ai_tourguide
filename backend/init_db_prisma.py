"""
使用 Prisma 初始化数据库表结构
"""
import asyncio
from prisma import Prisma

async def init_db():
    """使用 Prisma 创建所有表"""
    prisma = Prisma()
    await prisma.connect()
    
    try:
        # Prisma 会自动根据 schema.prisma 创建表
        # 运行迁移命令：prisma db push 或 prisma migrate dev
        print("Prisma 客户端已连接")
        print("请运行以下命令来创建数据库表：")
        print("  prisma db push")
        print("或者：")
        print("  prisma migrate dev --name init")
    finally:
        await prisma.disconnect()

if __name__ == "__main__":
    asyncio.run(init_db())

