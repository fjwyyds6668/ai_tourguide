# Prisma 设置指南

## 安装 Prisma

1. 安装 Python 依赖：
```powershell
pip install -r requirements.txt
```

2. 生成 Prisma 客户端：
```powershell
prisma generate
```

## 配置数据库

在 `backend/.env` 文件中设置 `DATABASE_URL`：

```env
DATABASE_URL="postgresql://postgres:123456@localhost:5432/ai_tourguide"
```

## 创建数据库表

### 方法 1：使用 db push（开发环境，快速）

```powershell
prisma db push
```

这会根据 `prisma/schema.prisma` 直接创建或更新数据库表结构。

### 方法 2：使用 migrate（生产环境，推荐）

```powershell
# 创建初始迁移
prisma migrate dev --name init

# 应用迁移
prisma migrate deploy
```

## 优势

✅ **避免编码问题**：Prisma 使用自己的连接管理，完全避免 psycopg2 的编码问题  
✅ **类型安全**：自动生成类型化的客户端  
✅ **现代化**：使用 async/await，性能更好  
✅ **自动迁移**：数据库结构变更管理更简单  
✅ **开发体验**：更好的 IDE 支持和自动补全

## 使用 Prisma 客户端

在代码中使用：

```python
from app.core.prisma_client import get_prisma

async def some_function():
    prisma = await get_prisma()
    users = await prisma.user.find_many()
    return users
```

## 注意事项

1. Prisma 需要先运行 `prisma generate` 生成客户端
2. 数据库表结构通过 `prisma/schema.prisma` 定义
3. 使用 `prisma db push` 或 `prisma migrate dev` 创建表

