# 景区 AI 数字人导游系统

一个基于前后端分离架构的智能景区导览系统，集成语音识别、语音合成、GraphRAG 检索和多种数据库技术。

## 技术栈

### 后端
- **框架**: Python FastAPI
- **数据库**: 
  - PostgreSQL (关系型数据)
  - Neo4j (图数据库)
  - Milvus (向量数据库)
- **AI 能力**:
  - 语音识别: Whisper / Vosk
  - 语音合成: Azure TTS / Edge TTS
  - GraphRAG 检索

### 前端
- **游客端**: Vue3
- **管理员端**: React

## 项目结构

```
ai_tourguide/
├── backend/              # FastAPI 后端
│   ├── app/
│   │   ├── api/         # API 路由
│   │   ├── core/        # 核心配置
│   │   ├── models/      # 数据模型
│   │   ├── services/    # 业务逻辑
│   │   └── utils/       # 工具函数
│   ├── requirements.txt
│   └── main.py
├── frontend-tourist/     # Vue3 游客端
├── frontend-admin/       # React 管理员端
└── README.md
```

## 功能模块

### 游客端
- 沉浸式语音导览
- 个性化景点推荐
- 实时语音交互
- 景点信息查询

### 管理员端
- 知识库维护
- 数据分析支持
- 内容管理
- 用户数据统计

## 快速开始

### 环境要求

- Python 3.9+
- Node.js 16+
- PostgreSQL 12+
- Docker（用于 Neo4j、Milvus、MinIO）

### 1. 启动数据库服务（Docker）

```bash
# 启动所有数据库服务
docker-compose up -d neo4j standalone minio etcd

# 或单独启动
docker-compose up -d neo4j      # Neo4j 图数据库
docker-compose up -d standalone  # Milvus 向量数据库
docker-compose up -d minio       # MinIO 对象存储
```

### 2. 后端设置

#### 安装 Python 依赖

```bash
cd backend
pip install -r requirements.txt
```

#### 配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
```

编辑 `backend/.env` 文件：

```env
# PostgreSQL 数据库
DATABASE_URL=postgresql://postgres:123456@localhost:5432/ai_tourguide

# Neo4j 图数据库
NEO4J_URI=bolt://localhost:30001
NEO4J_USER=neo4j
NEO4J_PASSWORD=12345678

# Milvus 向量数据库
MILVUS_HOST=localhost
MILVUS_PORT=30002

# OpenAI API（兼容硅基流动）
OPENAI_API_KEY=your-api-key
OPENAI_API_BASE=https://api.siliconflow.cn/v1
OPENAI_MODEL=Pro/deepseek-ai/DeepSeek-R1

# JWT 密钥
SECRET_KEY=your-secret-key-change-in-production
```

#### 初始化数据库

**使用 Prisma（推荐）**：

```bash
cd backend
# 生成 Prisma 客户端
prisma generate

# 创建数据库表（开发环境）
prisma db push

# 或使用迁移（生产环境）
prisma migrate dev --name init
```

**或使用传统方式**：

```bash
# 创建 PostgreSQL 数据库
createdb ai_tourguide

# 初始化表结构
python init_db.py
```

#### 启动后端服务

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 18000 --reload
```

后端服务将在 http://localhost:18000 启动

### 3. 前端启动

**游客端 (Vue3)**
```bash
cd frontend-tourist
npm install
npm run dev
```
访问: http://localhost:5173

**管理员端 (React)**
```bash
cd frontend-admin
npm install
npm start
```
访问: http://localhost:3000

## 服务端口总览

| 服务名称 | IP | 端口 | 访问地址 | 说明 |
|---------|----|----|---------|------|
| **后端 API** | 0.0.0.0 | 18000 | http://localhost:18000 | FastAPI 后端服务 |
| **前端管理端** | localhost | 3000 | http://localhost:3000 | React 管理后台 |
| **前端游客端** | localhost | 5173 | http://localhost:5173 | Vue3 游客端 |
| **PostgreSQL** | localhost | 5432 | localhost:5432 | 主数据库 |
| **Neo4j HTTP** | localhost | 30000 | http://localhost:30000 | Neo4j Browser |
| **Neo4j Bolt** | localhost | 30001 | bolt://localhost:30001 | Neo4j 数据库连接 |
| **Milvus API** | localhost | 30002 | localhost:30002 | Milvus 向量数据库 |
| **Milvus 健康检查** | localhost | 30003 | http://localhost:30003/healthz | Milvus 健康检查 |
| **Milvus Insight** | localhost | 30006 | http://localhost:30006 | Milvus Web 管理界面 |
| **MinIO API** | localhost | 30004 | http://localhost:30004 | MinIO 对象存储 |
| **MinIO 控制台** | localhost | 30005 | http://localhost:30005 | MinIO Web 管理界面 |

## API 文档

启动后端服务后，访问以下地址查看 API 文档：

- Swagger UI: http://localhost:18000/docs
- ReDoc: http://localhost:18000/redoc
- 健康检查: http://localhost:18000/health

## 主要功能

### 语音交互流程

1. 用户通过前端录音
2. 音频上传到后端进行语音识别（Whisper/Vosk）
3. 识别文本通过 GraphRAG 检索相关知识
4. 生成回复文本
5. 使用 TTS 合成语音（Azure/Edge TTS）
6. 返回音频给前端播放

### GraphRAG 检索

- **向量检索**: 使用 Milvus 进行语义相似度搜索
- **图检索**: 使用 Neo4j 进行实体关系查询
- **混合检索**: 结合向量和图数据库结果，提供更准确的答案

### 数据存储

- **PostgreSQL**: 存储用户、景点、交互记录等结构化数据
- **Neo4j**: 存储景点之间的关系、推荐路径等图数据
- **Milvus**: 存储知识库的向量嵌入，支持语义搜索

## 详细文档

- [项目结构说明](PROJECT_STRUCTURE.md) - 详细的目录结构和模块说明
- [GraphRAG 技术指南](GRAPH_RAG_GUIDE.md) - GraphRAG 实现和数据导入指南
- [数字人角色配置](数字人角色配置说明.md) - Live2D 数字人角色配置说明

## 语音服务配置

### Whisper（语音识别）

Whisper 会自动下载模型，首次使用需要网络连接。

### Vosk（语音识别）

需要下载中文模型：
```bash
wget https://alphacephei.com/vosk/models/vosk-model-cn-0.22.zip
unzip vosk-model-cn-0.22.zip
```

### Azure TTS（语音合成）

1. 在 Azure 门户创建语音服务
2. 获取 API 密钥和区域
3. 配置到 `.env`

### Edge TTS（语音合成）

无需配置，可直接使用。支持重试机制和连接错误处理。

### 离线本地 TTS（Bert-VITS2，高质量语音合成）

当你遇到 Edge TTS 403/网络限制时，可以使用 **Bert-VITS2** 在本机离线合成高质量语音，支持声音克隆和多说话人。

#### 1. 准备 Bert-VITS2 模型

确保已克隆 Bert-VITS2 项目到项目根目录，并准备好模型文件：

- 配置文件：`Bert-VITS2/configs/config.json`
- 模型文件：`Bert-VITS2/models/G_latest.pth`（或其他 .pth 模型文件）

#### 2. 安装依赖

```bash
pip install torch soundfile librosa pypinyin cn2an pyyaml
```

#### 3. 配置 `.env`

在 `backend/.env` 中添加以下配置：

```env
# 启用离线 TTS（Edge TTS 失败时自动降级到 Bert-VITS2）
LOCAL_TTS_ENABLED=true

# 可选：强制始终使用本地 TTS（不走 Edge TTS）
# LOCAL_TTS_FORCE=false

# Bert-VITS2 配置文件路径
BERTVITS2_CONFIG_PATH=Bert-VITS2/configs/config.json

# Bert-VITS2 模型文件路径
BERTVITS2_MODEL_PATH=Bert-VITS2/models/G_latest.pth

# Bert-VITS2 设备（cpu/cuda，如果有 GPU 建议使用 cuda）
BERTVITS2_DEVICE=cpu

# Bert-VITS2 默认说话人（可选，留空使用模型中的第一个说话人）
# BERTVITS2_DEFAULT_SPEAKER=

# Bert-VITS2 语言（仅支持中文 ZH）
BERTVITS2_LANGUAGE=ZH
```

#### 4. 使用方法

**API 调用：**
```bash
curl -X POST http://localhost:18000/api/v1/voice/synthesize \
  -H "Content-Type: application/json" \
  -d '{
    "text": "你好，这是测试",
    "voice": "说话人名称"
  }' \
  --output speech.wav
```

**Python 代码调用：**
```python
from app.services.voice_service import voice_service

# 使用默认说话人
audio_path = await voice_service.synthesize_local_bertvits2(
    text="你好，这是测试"
)

# 使用指定说话人
audio_path = await voice_service.synthesize_local_bertvits2(
    text="你好，这是测试",
    voice="说话人名称"
)
```

#### 5. 说话人选择规则

`/api/v1/voice/synthesize` 会：

- 优先用 Edge TTS
- 如果 Edge 失败且 `LOCAL_TTS_ENABLED=true`，自动降级到 Bert-VITS2

说话人选择规则：

- `voice` 传入说话人名称会使用对应说话人
- 如果未指定或说话人不存在，使用 `BERTVITS2_DEFAULT_SPEAKER` 或模型中的第一个说话人

你可以把角色表的 `voice` 字段改成 Bert-VITS2 说话人名称，即可实现多角色多音色离线播报。

#### 6. 测试

```bash
# 测试基础功能
cd backend
python test_bertvits2.py --text "你好，我是离线语音测试" --voice "说话人名称" --out test.wav
```

#### 7. 常见问题

**Q: 首次运行很慢？**  
A: 首次运行会加载模型（可能需要几秒到几十秒），后续运行会快很多。

**Q: 如何查看可用的说话人？**  
A: 说话人列表在模型的 `config.json` 中的 `spk2id` 字段定义，或查看模型训练时的配置。

**Q: 如何添加新说话人？**  
A: 需要重新训练模型或使用支持多说话人的预训练模型。

**Q: 模型文件在哪里？**  
A: 模型文件需要从 Bert-VITS2 项目获取，或使用自己训练的模型。

## 常见问题

### 1. 数据库连接失败

- 检查 `.env` 中的数据库配置是否正确
- 确保数据库服务已启动
- PostgreSQL: 检查端口 5432 是否被占用
- Neo4j: 检查 Docker 容器是否运行 `docker ps | grep neo4j`
- Milvus: 检查端口 30002 是否可访问

### 2. Prisma 客户端未生成

```bash
cd backend
prisma generate
```

### 3. 端口冲突

如果端口被占用：
- 修改配置文件中的端口
- 或停止占用端口的进程

### 4. CORS 错误

后端已配置允许的源：
- `http://localhost:3000`（管理端）
- `http://localhost:5173`（游客端）

如需添加其他源，修改 `backend/app/core/config.py` 中的 `CORS_ORIGINS`

### 5. 语音识别失败

- **Whisper**: 确保有足够的磁盘空间（模型约 1.5GB）
- **Vosk**: 确保模型文件路径正确

### 6. Edge TTS 连接失败

Edge TTS 已实现自动重试机制（最多 5 次），如果持续失败：
- 检查网络连接
- 检查防火墙设置
- 稍后重试

## 开发建议

1. 使用虚拟环境管理 Python 依赖
2. 定期备份数据库
3. 生产环境使用 HTTPS
4. 配置适当的 CORS 策略
5. 使用 Prisma 进行数据库操作（避免编码问题）

## 开发计划

- [ ] 完善用户认证系统
- [ ] 实现个性化推荐算法
- [ ] 添加实时位置服务
- [ ] 优化语音识别准确率
- [ ] 增强 GraphRAG 检索效果
- [ ] 添加多语言支持

## 许可证

MIT License
