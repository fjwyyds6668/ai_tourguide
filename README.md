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

### 后端启动

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

### 前端启动

**游客端 (Vue3)**
```bash
cd frontend-tourist
npm install
npm run dev
```

**管理员端 (React)**
```bash
cd frontend-admin
npm install
npm start
```

## 环境配置

创建 `.env` 文件配置数据库连接和 API 密钥（参考 `backend/.env.example`）

详细设置步骤请参考 [SETUP.md](SETUP.md)

## API 文档

启动后端服务后，访问以下地址查看 API 文档：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

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

## 开发计划

- [ ] 完善用户认证系统
- [ ] 实现个性化推荐算法
- [ ] 添加实时位置服务
- [ ] 优化语音识别准确率
- [ ] 增强 GraphRAG 检索效果
- [ ] 添加多语言支持

## 许可证

MIT License

