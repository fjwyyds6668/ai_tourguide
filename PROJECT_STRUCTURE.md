# 项目结构说明

## 目录结构

```
ai_tourguide/
├── backend/                      # FastAPI 后端
│   ├── app/
│   │   ├── api/                  # API 路由模块
│   │   │   ├── __init__.py       # 路由注册
│   │   │   ├── voice.py          # 语音相关 API
│   │   │   ├── rag.py            # GraphRAG 检索 API
│   │   │   ├── attractions.py   # 景点管理 API
│   │   │   └── admin.py          # 管理员 API
│   │   ├── core/                 # 核心配置模块
│   │   │   ├── config.py         # 应用配置
│   │   │   ├── database.py       # PostgreSQL 连接
│   │   │   ├── neo4j_client.py  # Neo4j 客户端
│   │   │   └── milvus_client.py  # Milvus 客户端
│   │   ├── models/               # 数据模型
│   │   │   ├── __init__.py
│   │   │   ├── attraction.py    # 景点模型
│   │   │   ├── user.py          # 用户模型
│   │   │   └── interaction.py   # 交互记录模型
│   │   ├── services/             # 业务逻辑服务
│   │   │   ├── __init__.py
│   │   │   ├── voice_service.py # 语音识别/合成服务
│   │   │   └── rag_service.py   # GraphRAG 检索服务
│   │   └── utils/                # 工具函数
│   │       ├── __init__.py
│   │       └── auth.py          # 认证工具
│   ├── main.py                   # FastAPI 应用入口
│   ├── init_db.py                # 数据库初始化脚本
│   ├── requirements.txt          # Python 依赖
│   └── .env.example              # 环境变量示例
│
├── frontend-tourist/             # Vue3 游客端
│   ├── src/
│   │   ├── api/                  # API 调用
│   │   │   └── index.js
│   │   ├── views/                # 页面组件
│   │   │   ├── Home.vue         # 首页
│   │   │   ├── VoiceGuide.vue   # 语音导览
│   │   │   └── Attractions.vue  # 景点列表
│   │   ├── router/               # 路由配置
│   │   │   └── index.js
│   │   ├── App.vue              # 根组件
│   │   └── main.js              # 入口文件
│   ├── package.json
│   └── vite.config.js
│
├── frontend-admin/               # React 管理员端
│   ├── src/
│   │   ├── api/                  # API 调用
│   │   │   └── index.js
│   │   ├── components/           # 组件
│   │   │   └── Sidebar.js       # 侧边栏
│   │   ├── pages/                # 页面
│   │   │   ├── Dashboard.js     # 仪表盘
│   │   │   ├── KnowledgeBase.js # 知识库管理
│   │   │   ├── Analytics.js     # 数据分析
│   │   │   └── AttractionsManagement.js # 景点管理
│   │   ├── App.js               # 根组件
│   │   └── index.js             # 入口文件
│   └── package.json
│
├── docker-compose.yml            # Docker 编排配置
├── README.md                     # 项目说明
├── SETUP.md                      # 设置指南
└── PROJECT_STRUCTURE.md          # 本文件
```

## 核心模块说明

### 后端模块

#### API 路由 (`app/api/`)
- **voice.py**: 处理语音识别和合成请求
- **rag.py**: 提供 GraphRAG 检索接口
- **attractions.py**: 景点 CRUD 操作
- **admin.py**: 管理员功能（知识库上传、数据分析）

#### 核心服务 (`app/core/`)
- **config.py**: 统一管理配置（数据库、API 密钥等）
- **database.py**: PostgreSQL 连接池管理
- **neo4j_client.py**: Neo4j 图数据库客户端
- **milvus_client.py**: Milvus 向量数据库客户端

#### 业务服务 (`app/services/`)
- **voice_service.py**: 
  - 语音识别：Whisper（云端）和 Vosk（本地）
  - 语音合成：Azure TTS 和 Edge TTS
- **rag_service.py**:
  - 向量检索：使用 Milvus 进行语义搜索
  - 图检索：使用 Neo4j 查询实体关系
  - 混合检索：结合两种检索方式

#### 数据模型 (`app/models/`)
- **attraction.py**: 景点信息（名称、描述、位置、坐标等）
- **user.py**: 用户信息（游客和管理员）
- **interaction.py**: 用户交互记录（查询、推荐等）

### 前端模块

#### 游客端 (Vue3)
- **Home.vue**: 功能入口页面
- **VoiceGuide.vue**: 语音交互界面，支持录音、识别、合成
- **Attractions.vue**: 景点浏览和搜索

#### 管理员端 (React)
- **Dashboard.js**: 数据概览（用户数、景点数、交互次数）
- **KnowledgeBase.js**: 知识库内容管理
- **Analytics.js**: 交互数据分析和热门景点统计
- **AttractionsManagement.js**: 景点信息管理

## 数据流

### 语音导览流程

```
用户录音 → 前端上传 → 后端识别(Whisper/Vosk) 
→ 文本查询 → GraphRAG检索 → 生成回复 
→ TTS合成(Azure/Edge) → 返回音频 → 前端播放
```

### GraphRAG 检索流程

```
用户查询 → 生成向量嵌入 → Milvus向量搜索 
→ 提取实体 → Neo4j图搜索 → 合并结果 
→ 生成回复
```

## 数据库设计

### PostgreSQL (关系数据)
- `users`: 用户表
- `attractions`: 景点表
- `interactions`: 交互记录表

### Neo4j (图数据)
- 节点：景点、用户、类别
- 关系：相邻、推荐、访问过

### Milvus (向量数据)
- Collection: `tour_knowledge`
- Fields: `id`, `text_id`, `embedding` (384维)

## 扩展建议

1. **认证系统**: 完善 JWT 认证，添加用户注册/登录
2. **推荐算法**: 基于图数据库实现个性化推荐
3. **实时通信**: 使用 WebSocket 实现实时语音流
4. **缓存层**: 添加 Redis 缓存热门查询
5. **日志系统**: 集成日志收集和分析
6. **监控告警**: 添加系统监控和异常告警

