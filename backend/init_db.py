"""
初始化数据库表结构
"""
from app.core.database import engine, Base
from app.models import Attraction, User, Interaction

def init_db():
    """创建所有表"""
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")

if __name__ == "__main__":
    init_db()

