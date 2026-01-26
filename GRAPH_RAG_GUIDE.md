# GraphRAG 技术实现指南

## 什么是 GraphRAG？

GraphRAG（Graph Retrieval-Augmented Generation）是一种结合图数据库和向量检索的增强生成技术。它通过以下方式提升 RAG 系统的能力：

1. **结构化知识存储**：使用图数据库存储实体和关系
2. **语义检索**：使用向量数据库进行语义相似度搜索
3. **关系推理**：通过图结构发现实体之间的隐含关系
4. **上下文增强**：结合向量和图检索结果生成更丰富的上下文

## 本项目的 GraphRAG 实现

### 核心组件

#### 1. 实体识别（NER）
- **位置**: `backend/app/services/rag_service.py` - `extract_entities()`
- **技术**: 使用 jieba 进行中文分词和词性标注
- **功能**: 从文本中提取实体（地名、人名、机构名等）

```python
entities = rag_service.extract_entities("我想了解天安门广场的历史")
# 返回: [{"text": "天安门广场", "type": "LOCATION", "confidence": 0.8}]
```

#### 2. 向量检索
- **位置**: `backend/app/services/rag_service.py` - `vector_search()`
- **技术**: Milvus 向量数据库 + Sentence Transformers
- **功能**: 在知识库中进行语义相似度搜索

#### 3. 图检索
- **位置**: `backend/app/services/rag_service.py` - `graph_search()` 和 `graph_subgraph_search()`
- **技术**: Neo4j 图数据库
- **功能**: 
  - 查询实体之间的关系
  - 构建实体子图
  - 发现多跳关系

#### 4. 混合检索（GraphRAG 核心）
- **位置**: `backend/app/services/rag_service.py` - `hybrid_search()`
- **工作流程**:
  1. 向量检索获取语义相似内容
  2. 实体识别提取关键实体
  3. 图检索查询实体关系
  4. 结果融合生成增强上下文

### 知识图谱构建

#### 图构建服务
- **位置**: `backend/app/services/graph_builder.py`
- **功能**:
  - 创建实体节点
  - 建立实体关系
  - 批量构建景点图谱

#### 自动图构建
当上传知识库内容时，系统会：
1. 存储向量嵌入到 Milvus
2. 提取实体并创建图节点
3. 建立文本-实体关系

## API 使用示例

### 1. GraphRAG 混合检索

```bash
POST /api/v1/rag/search
{
  "query": "天安门附近有什么景点？",
  "top_k": 5
}
```

**返回结果**:
```json
{
  "vector_results": [...],      // 向量检索结果
  "graph_results": [...],        // 图检索结果
  "subgraph": {...},            // 实体子图
  "entities": [...],            // 识别的实体
  "enhanced_context": "...",     // 融合后的上下文
  "query": "天安门附近有什么景点？"
}
```

### 2. 知识库上传（自动构建图）

```bash
POST /api/v1/admin/knowledge/upload
{
  "items": [
    {
      "text": "天安门广场位于北京市中心，是中国的象征。",
      "text_id": "kb_001",
      "metadata": {}
    }
  ],
  "build_graph": true
}
```

系统会自动：
- 提取实体："天安门广场"、"北京市"、"中国"
- 创建图节点和关系
- 存储向量嵌入

### 3. 图数据库操作

```bash
# 获取实体子图
GET /api/v1/graph/subgraph?entities=天安门,故宫&depth=2

# 创建节点
POST /api/v1/graph/nodes
{
  "name": "天安门",
  "labels": ["Attraction", "Landmark"],
  "properties": {"category": "历史建筑"}
}

# 创建关系
POST /api/v1/graph/relationships
{
  "from_entity": "天安门",
  "to_entity": "故宫",
  "relation_type": "NEARBY",
  "properties": {"distance": 1.2}
}
```

## GraphRAG 工作流程

```
用户查询
    ↓
[1] 向量检索 (Milvus)
    → 获取语义相似文本
    ↓
[2] 实体识别 (jieba NER)
    → 提取: ["天安门", "景点", "附近"]
    ↓
[3] 图检索 (Neo4j)
    → 查询实体关系
    → 构建子图
    ↓
[4] 结果融合
    → 合并向量和图结果
    → 生成增强上下文
    ↓
[5] 生成回复
    → 基于增强上下文生成答案
```

## 优势

### 相比传统 RAG
1. **关系理解**：不仅能找到相关文本，还能理解实体关系
2. **多跳推理**：通过图结构进行多跳关系查询
3. **结构化知识**：图数据库提供结构化的知识表示

### 应用场景
- **景点推荐**：基于地理位置和类别关系推荐
- **路径规划**：通过图结构找到最优游览路径
- **知识问答**：结合文本和图结构回答复杂问题

## 配置和优化

### 实体识别优化
- 添加自定义词典（景点名称等）
- 调整词性过滤规则
- 使用更高级的 NER 模型（如 spaCy 中文模型）

### 图查询优化
- 创建索引加速查询
- 优化 Cypher 查询语句
- 限制子图深度和节点数量

### 结果融合策略
- 调整向量和图结果的权重
- 实现更智能的排序算法
- 添加结果去重和过滤

## 扩展方向

1. **多模态 GraphRAG**：结合图像和文本构建多模态图
2. **时序 GraphRAG**：考虑时间维度的关系
3. **动态图更新**：实时更新图结构
4. **图神经网络**：使用 GNN 进行更复杂的推理

---

## 数据导入指南

### 前置条件

#### 1. 确保服务已启动

```bash
# 启动 Neo4j 和 Milvus（如果使用 Docker）
docker-compose up -d neo4j standalone

# 或者单独启动
docker-compose up -d neo4j
docker-compose up -d standalone  # Milvus
```

#### 2. 确保数据库连接配置正确

检查 `backend/.env` 文件中的配置：

```env
# PostgreSQL（用于读取 attractions 数据）
DATABASE_URL=postgresql://postgres:123456@localhost:5432/ai_tourguide

# Neo4j（图数据库）
NEO4J_URI=bolt://localhost:17687
NEO4J_USER=neo4j
NEO4J_PASSWORD=12345678

# Milvus（向量数据库）
MILVUS_HOST=localhost
MILVUS_PORT=19530
```

#### 3. 确保 Prisma 客户端已生成

```bash
cd backend
prisma generate
```

### 执行导入

#### 方式一：使用命令行脚本（推荐）

在 `backend` 目录下执行：

```bash
# 导入所有景点数据（同时写入 Milvus 和 Neo4j）
python import_graphrag_data.py --source attractions --collection tour_knowledge --build-graph --build-attraction-graph

# 只导入前 5 条数据（测试用）
python import_graphrag_data.py --source attractions --collection tour_knowledge --build-graph --build-attraction-graph --limit 5

# 只构建景点图结构（不构建文本-实体图）
python import_graphrag_data.py --source attractions --collection tour_knowledge --build-attraction-graph

# 只写入向量数据库（不构建图）
python import_graphrag_data.py --source attractions --collection tour_knowledge
```

#### 方式二：使用 API 接口

通过管理后台或 API 调用：

```bash
# 使用 curl
curl -X POST "http://localhost:18000/api/v1/admin/data/import_attractions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "collection_name": "tour_knowledge",
    "build_graph": true,
    "build_attraction_graph": true
  }'
```

或在管理后台的"数据导入"页面点击"导入景点数据"按钮。

### 参数说明

- `--source attractions`: 数据源，当前只支持从 attractions 表导入
- `--collection tour_knowledge`: Milvus 集合名称（默认：tour_knowledge）
- `--build-graph`: 是否构建文本-实体图（Text/Entity/MENTIONS 关系）
- `--build-attraction-graph`: 是否构建景点图（Attraction/NEARBY 关系）
- `--limit N`: 限制导入数量（用于测试）

### 导入内容

#### 1. 向量数据库（Milvus）

每个景点会生成一个文本描述，包含：
- 景点名称
- 类别
- 位置
- 介绍
- 坐标

文本会被转换为 384 维向量并存储到 Milvus。

#### 2. 图数据库（Neo4j）

**如果启用 `--build-graph`：**
- **Text 节点**：每个景点的文本描述
- **Entity 节点**：从文本中提取的实体（地名、人名等）
- **MENTIONS 关系**：Text → Entity（文本提及实体）

**如果启用 `--build-attraction-graph`：**
- **Attraction 节点**：景点节点，包含完整信息
- **NEARBY 关系**：相同类别的景点之间建立 NEARBY 关系

### 验证导入结果

#### 检查 Milvus

```python
from pymilvus import connections, Collection

connections.connect(alias="default", host="localhost", port=19530)
collection = Collection("tour_knowledge")
collection.load()
print(f"向量数量: {collection.num_entities}")
```

#### 检查 Neo4j

访问 Neo4j Browser: http://localhost:17474

执行查询：

```cypher
// 查看所有景点节点
MATCH (a:Attraction) RETURN a LIMIT 10

// 查看文本节点
MATCH (t:Text) RETURN t LIMIT 10

// 查看实体节点
MATCH (e:ENTITY) RETURN e LIMIT 10

// 查看关系
MATCH (a:Attraction)-[r:NEARBY]->(b:Attraction) RETURN a, r, b LIMIT 10
```

### 常见问题

#### 1. 连接失败

- 检查 Neo4j 和 Milvus 服务是否运行
- 检查端口是否正确（Neo4j: 17687, Milvus: 19530）
- 检查防火墙设置

#### 2. Prisma 客户端未生成

```bash
cd backend
prisma generate
```

#### 3. 依赖缺失

```bash
pip install -r requirements.txt
```

#### 4. 导入速度慢

- 向量生成需要时间，大量数据建议分批导入
- 可以使用 `--limit` 参数先测试少量数据

### 下一步

导入完成后，可以：

1. 使用 GraphRAG 检索：`POST /api/v1/rag/search`
2. 查询图结构：`GET /api/v1/graph/subgraph?entities=景点名`
3. 在管理后台查看导入的数据

