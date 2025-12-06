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

