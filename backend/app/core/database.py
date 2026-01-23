"""
数据库连接管理 - 现代化配置方式
使用 DATABASE_URL 环境变量，通过 Pydantic 验证，避免编码问题
"""
import os

# 设置 PostgreSQL 客户端编码为 UTF-8
os.environ['PGCLIENTENCODING'] = 'UTF8'

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# 使用 DATABASE_URL 创建数据库引擎
# 直接使用 URL 字符串，SQLAlchemy 会自动处理编码问题
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # 连接前检查连接是否有效
    pool_size=10,  # 连接池大小
    max_overflow=20,  # 最大溢出连接数
    echo=False  # 是否打印 SQL 语句（生产环境设为 False）
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# 依赖注入：获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

