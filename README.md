# 景区 AI 数字人导游系统

> 对应毕设：第1章 绪论

一个基于前后端分离架构的智能景区导览系统，集成语音识别、语音合成、GraphRAG 检索和多种数据库技术，为游客提供沉浸式数字人语音导览服务。

---

## 1. 相关技术（第2章）

### 1.1 数字人技术

- **建模与渲染**：Live2D 数字人形象，支持多角色配置
- **语音识别**：Whisper / Vosk
- **语音合成**：科大讯飞 TTS（在线）/ CosyVoice2（本地备用）
- **多模态交互**：语音输入 → 文本检索 → 语音输出，流式文本与 TTS 同步

### 1.2 知识库与检索技术

- **增强型检索生成（RAG）**：向量检索 + 图检索混合，结合 LLM 生成
- **向量数据库**：Milvus 语义相似度搜索
- **图数据库**：Neo4j 实体关系查询、景点推荐路径

### 1.3 系统开发关键技术

- **多数据库协同**：PostgreSQL（结构化）、Neo4j（图）、Milvus（向量）、MinIO（对象存储）
- **前后端实时交互**：REST API、SSE 流式输出、WebSocket 语音流

---

## 2. 功能模块（第3章 需求分析）

### 2.1 游客端功能

- 沉浸式语音导览
- 个性化景点推荐
- 实时语音交互
- 景点信息查询

### 2.2 管理端功能

- 知识库维护
- 数据分析支持
- 内容管理（景点、角色等）
- 用户数据统计

### 2.3 知识库与数据分析功能

- 知识文档导入、向量化与图构建
- 访问量、交互类型等统计与可视化

---

## 3. 系统架构与运行环境（第3章 3.4、第4章 4.2）

### 3.1 系统运行环境

| 类别 | 要求 |
|------|------|
| **操作系统** | Windows 10+ / Linux / macOS |
| **Python** | 3.9+（推荐 3.10~3.12） |
| **Node.js** | 16+（推荐 18+） |
| **PostgreSQL** | 12+ |
| **Docker** | 20+（Neo4j、Milvus、MinIO） |
| **内存** | 建议 8GB+（本地 TTS 需 16GB+） |
| **磁盘** | 建议 10GB+（含模型与数据） |

### 3.2 核心依赖版本

- **后端**：FastAPI 0.115+、Prisma、Neo4j 5.x、Milvus 2.6+、sentence-transformers
- **游客端**：Vue 3、Vite 5、Element Plus
- **管理端**：React 18、Ant Design 5

### 3.3 项目结构

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
├── frontend-admin/       # React 管理端
└── README.md
```

---

## 4. 数据库与检索设计（第4章 4.4、4.5）

### 4.1 数据存储职责

| 数据库 | 职责 |
|--------|------|
| **PostgreSQL** | 用户、景点、角色、交互记录等结构化数据 |
| **Neo4j** | 景点关系、推荐路径等图数据 |
| **Milvus** | 知识库向量嵌入与语义搜索 |
| **MinIO** | 知识文档、图片等对象存储 |

### 4.2 检索生成流程

1. 用户语音/文本输入 → 语音识别（若为语音）
2. 向量检索（Milvus）获取语义相关片段
3. 图检索（Neo4j）补充实体关系与上下文
4. 混合结果送入 LLM 生成回复
5. TTS 合成语音返回前端播放

---

## 5. 快速开始（第5章 系统实现）

### 5.1 启动数据库服务

```bash
docker-compose up -d neo4j standalone minio etcd
```

### 5.2 后端设置

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # 填写 DATABASE_URL、NEO4J_*、MILVUS_*、OPENAI_API_KEY、SECRET_KEY 等
prisma generate
prisma db push
uvicorn main:app --host 0.0.0.0 --port 18000 --reload
```

### 5.3 前端启动

| 端 | 命令 | 访问地址 |
|----|------|----------|
| 游客端 | `cd frontend-tourist && npm install && npm run dev` | http://localhost:5173 |
| 管理端 | `cd frontend-admin && npm install && npm start` | http://localhost:3000 |

---

## 6. 语音与数字人配置

- **Whisper**：自动下载模型，首次使用需联网
- **Vosk**：需下载 [中文模型](https://alphacephei.com/vosk/models/vosk-model-cn-0.22.zip)
- **科大讯飞 TTS**：在 [开放平台](https://www.xfyun.cn/) 注册，配置 `XFYUN_*` 变量
- **CosyVoice2（本地备用）**：克隆 CosyVoice 到项目根目录，设置 `LOCAL_TTS_ENABLED=true` 等，详见 `.env.example`
- **数字人角色**：见 [数字人角色配置说明](数字人角色配置说明.md)

---

## 7. API 文档与端口

| 服务 | 端口 | 地址 |
|------|------|------|
| 后端 API | 18000 | http://localhost:18000 |
| Swagger UI | 18000 | http://localhost:18000/docs |
| ReDoc | 18000 | http://localhost:18000/redoc |
| PostgreSQL | 5432 | localhost:5432 |
| Neo4j Browser | 30000 | http://localhost:30000 |
| Neo4j Bolt | 30001 | bolt://localhost:30001 |
| Milvus | 30002 | localhost:30002 |
| MinIO 控制台 | 30005 | http://localhost:30005 |

---

## 8. 系统测试说明（第6章）

- **功能测试**：游客端语音导览、景点查询、管理端知识库与数据统计
- **性能测试**：检索准确率、响应时间、并发能力
- 详细测试用例与结果见论文第6章

---

## 9. 常见问题

1. **数据库连接失败**：检查 `.env` 配置，确认 PostgreSQL、Neo4j、Milvus 已启动
2. **Prisma 客户端未生成**：执行 `cd backend && prisma generate`
3. **CORS 错误**：在 `config.py` 的 `CORS_ORIGINS` 中添加新源
4. **TTS/语音识别失败**：Whisper 需约 1.5GB 磁盘；科大讯飞失败时可启用 CosyVoice2 备用

---

## 10. 开发计划与展望（第7章）

**系统优化亮点**：RAG 检索优化（参数配置化、向量缓存、批量 Neo4j、并行簇构建）；错误可观测性（`errors` 字段、结构化日志）；配置与安全（上传白名单、路径约束）；可维护性（RAG 模块拆分、统一分页）。

**后续计划**：
- [ ] 完善用户认证系统
- [ ] 实现个性化推荐算法
- [ ] 添加实时位置服务
- [ ] 优化语音识别准确率
- [ ] 增强 GraphRAG 检索效果
- [ ] 添加多语言支持

---

## 11. 详细文档

- [项目结构说明](PROJECT_STRUCTURE.md)
- [GraphRAG 技术指南](GRAPH_RAG_GUIDE.md)
- [数字人角色配置](数字人角色配置说明.md)

---

## 许可证

MIT License
