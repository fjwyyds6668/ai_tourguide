"""初始化数据库表结构"""
import os

os.environ['PGCLIENTENCODING'] = 'UTF8'
os.environ['PYTHONIOENCODING'] = 'utf-8'

from app.core.database import engine, Base
from app.models import Attraction, User, Interaction  # noqa: F401

def init_db():
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")

if __name__ == "__main__":
    init_db()

