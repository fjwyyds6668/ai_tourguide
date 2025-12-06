# 项目设置指南

## 环境要求

- Python 3.9+
- Node.js 16+
- PostgreSQL 12+
- Neo4j 4.0+
- Milvus 2.0+

## 后端设置

### 1. 安装 Python 依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置数据库连接信息。

### 3. 初始化数据库

```bash
# 创建 PostgreSQL 数据库
createdb ai_tourguide

# 初始化表结构
python init_db.py
```

### 4. 启动后端服务

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 前端设置

### 游客端 (Vue3)

```bash
cd frontend-tourist
npm install
npm run dev
```

访问: http://localhost:5173

### 管理员端 (React)

```bash
cd frontend-admin
npm install
npm start
```

访问: http://localhost:3000

## 数据库配置

### PostgreSQL

```sql
CREATE DATABASE ai_tourguide;
```

### Neo4j

1. 下载并安装 Neo4j Desktop
2. 创建新数据库
3. 配置连接信息到 `.env`

### Milvus

1. 使用 Docker 启动 Milvus:

```bash
docker-compose up -d
```

或参考 [Milvus 官方文档](https://milvus.io/docs/install_standalone-docker.md)

## 语音服务配置

### Whisper

Whisper 会自动下载模型，首次使用需要网络连接。

### Vosk

需要下载中文模型：
```bash
wget https://alphacephei.com/vosk/models/vosk-model-cn-0.22.zip
unzip vosk-model-cn-0.22.zip
```

### Azure TTS

1. 在 Azure 门户创建语音服务
2. 获取 API 密钥和区域
3. 配置到 `.env`

### Edge TTS

无需配置，可直接使用。

## 常见问题

### 1. 数据库连接失败

检查 `.env` 中的数据库配置是否正确，确保数据库服务已启动。

### 2. Milvus 连接失败

确保 Milvus 服务正在运行：
```bash
docker ps | grep milvus
```

### 3. 语音识别失败

- Whisper: 确保有足够的磁盘空间（模型约 1.5GB）
- Vosk: 确保模型文件路径正确

## 开发建议

1. 使用虚拟环境管理 Python 依赖
2. 定期备份数据库
3. 生产环境使用 HTTPS
4. 配置适当的 CORS 策略

