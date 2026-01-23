"""
初始化数据库表结构
"""
import os

# 设置编码环境变量
os.environ['PGCLIENTENCODING'] = 'UTF8'
os.environ['PYTHONIOENCODING'] = 'utf-8'

from app.core.database import engine, Base
# 导入模型以确保 SQLAlchemy 能够发现并创建对应的表
from app.models import Attraction, User, Interaction  # noqa: F401

def init_db():
    """创建所有表"""
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")

if __name__ == "__main__":
    init_db()

