"""
GraphRAG 检索服务
GraphRAG: 结合图数据库和向量检索的增强生成技术
"""
import logging
import re
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
from app.core.milvus_client import milvus_client
from app.core.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)

# 尝试导入中文分词库
try:
    import jieba
    import jieba.posseg as pseg
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False
    logger.warning("jieba not available, using simple keyword extraction")

class RAGService:
    """
    GraphRAG 检索增强生成服务
    
    GraphRAG 核心功能：
    1. 实体识别（NER）：从查询中提取实体
    2. 向量检索：使用 Milvus 进行语义相似度搜索
    3. 图检索：使用 Neo4j 查询实体关系和子图
    4. 结果融合：结合向量和图检索结果生成增强上下文
    """
    
    def __init__(self):
        self.embedding_model = None
        self._init_embedding_model()
        self._init_ner()
    
    def _init_embedding_model(self):
        """初始化嵌入模型"""
        try:
            # 使用较小的多语言模型，维度为 384
            self.embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            logger.info("Embedding model loaded")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            self.embedding_model = None
    
    def _init_ner(self):
        """初始化实体识别"""
        if JIEBA_AVAILABLE:
            # 加载自定义词典（可以添加景点名称等）
            try:
                jieba.initialize()
                logger.info("NER model (jieba) initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize jieba: {e}")
    
    def extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """
        从文本中提取实体（命名实体识别）
        返回: [{"text": "实体名", "type": "实体类型", "start": 0, "end": 2}]
        """
        entities = []
        
        if JIEBA_AVAILABLE:
            # 使用 jieba 进行词性标注和实体识别
            words = pseg.cut(text)
            for word, flag in words:
                # 识别地名、机构名、人名等
                if flag in ['ns', 'nr', 'nt', 'nz'] or len(word) >= 2:
                    entities.append({
                        "text": word,
                        "type": self._map_pos_to_entity_type(flag),
                        "confidence": 0.8
                    })
        else:
            # 简单关键词提取（备用方案）
            # 提取2-4字的中文词组
            pattern = r'[\u4e00-\u9fa5]{2,4}'
            matches = re.finditer(pattern, text)
            for match in matches:
                entities.append({
                    "text": match.group(),
                    "type": "KEYWORD",
                    "confidence": 0.6
                })
        
        # 去重
        seen = set()
        unique_entities = []
        for entity in entities:
            if entity["text"] not in seen:
                seen.add(entity["text"])
                unique_entities.append(entity)
        
        return unique_entities
    
    def _map_pos_to_entity_type(self, pos: str) -> str:
        """将词性标注映射到实体类型"""
        mapping = {
            'ns': 'LOCATION',  # 地名
            'nr': 'PERSON',    # 人名
            'nt': 'ORG',       # 机构名
            'nz': 'OTHER',     # 其他专名
        }
        return mapping.get(pos, 'KEYWORD')
    
    def generate_embedding(self, text: str) -> List[float]:
        """生成文本嵌入向量"""
        if not self.embedding_model:
            raise ValueError("Embedding model not loaded")
        
        embedding = self.embedding_model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    
    async def vector_search(self, query: str, collection_name: str = "tour_knowledge", top_k: int = 5) -> List[Dict[str, Any]]:
        """向量相似度搜索"""
        if not milvus_client.connected:
            milvus_client.connect()
        
        # 生成查询向量
        query_vector = [self.generate_embedding(query)]
        
        # 获取集合
        collection = milvus_client.get_collection(collection_name)
        collection.load()
        
        # 搜索
        search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
        results = collection.search(
            data=query_vector,
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            output_fields=["text_id"]
        )
        
        # 格式化结果
        search_results = []
        if results and len(results) > 0:
            for hit in results[0]:
                search_results.append({
                    "id": hit.id,
                    "text_id": hit.entity.get("text_id", ""),
                    "distance": hit.distance,
                    "score": 1 / (1 + hit.distance) if hit.distance > 0 else 1.0  # 转换为相似度分数
                })
        
        return search_results
    
    async def graph_search(self, entity_name: str, relation_type: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        图数据库关系查询
        
        GraphRAG 核心：通过图结构查询实体之间的关系和上下文
        """
        if relation_type:
            query = """
            MATCH (a)-[r:%s]->(b)
            WHERE a.name CONTAINS $name OR b.name CONTAINS $name
            RETURN a, r, b, labels(a) as a_labels, labels(b) as b_labels, type(r) as rel_type
            LIMIT $limit
            """ % relation_type
        else:
            query = """
            MATCH (a)-[r]->(b)
            WHERE a.name CONTAINS $name OR b.name CONTAINS $name
            RETURN a, r, b, labels(a) as a_labels, labels(b) as b_labels, type(r) as rel_type
            LIMIT $limit
            """
        
        results = neo4j_client.execute_query(
            query,
            {"name": entity_name, "limit": limit}
        )
        
        return results
    
    async def graph_subgraph_search(self, entities: List[str], depth: int = 2) -> Dict[str, Any]:
        """
        图子图搜索：基于多个实体构建子图
        
        这是 GraphRAG 的核心功能之一，通过实体构建相关子图
        """
        if not entities:
            return {"nodes": [], "relationships": []}
        
        # 构建查询：查找实体之间的路径
        entity_list = "', '".join(entities)
        query = f"""
        MATCH path = (a)-[*1..{depth}]-(b)
        WHERE a.name IN ['{entity_list}'] OR b.name IN ['{entity_list}']
        WITH path, nodes(path) as nodes_list, relationships(path) as rels_list
        UNWIND nodes_list as node
        UNWIND rels_list as rel
        RETURN DISTINCT 
            id(node) as node_id,
            labels(node) as labels,
            properties(node) as properties,
            id(rel) as rel_id,
            type(rel) as rel_type,
            properties(rel) as rel_properties
        LIMIT 50
        """
        
        results = neo4j_client.execute_query(query)
        
        # 格式化结果
        nodes = {}
        relationships = []
        
        for record in results:
            if 'node_id' in record:
                node_id = record['node_id']
                if node_id not in nodes:
                    nodes[node_id] = {
                        "id": node_id,
                        "labels": record.get('labels', []),
                        "properties": record.get('properties', {})
                    }
            
            if 'rel_id' in record and record['rel_id']:
                relationships.append({
                    "id": record['rel_id'],
                    "type": record.get('rel_type'),
                    "properties": record.get('rel_properties', {})
                })
        
        return {
            "nodes": list(nodes.values()),
            "relationships": relationships,
            "entity_count": len(entities)
        }
    
    async def hybrid_search(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """
        GraphRAG 混合检索：结合向量搜索和图搜索
        
        工作流程：
        1. 向量检索：在知识库中查找语义相似的内容
        2. 实体识别：从查询和向量结果中提取实体
        3. 图检索：基于实体查询图数据库中的关系和子图
        4. 结果融合：合并向量和图检索结果，生成增强上下文
        """
        # 步骤1: 向量搜索
        vector_results = await self.vector_search(query, top_k=top_k)
        
        # 步骤2: 实体识别（GraphRAG 核心）
        entities = self.extract_entities(query)
        
        # 从向量搜索结果中也可能提取实体
        if vector_results:
            for result in vector_results[:3]:  # 只处理前3个结果
                text_id = result.get("text_id", "")
                if text_id:
                    # 假设 text_id 可能包含实体信息
                    entities.extend(self.extract_entities(text_id))
        
        # 去重实体
        unique_entities = {}
        for entity in entities:
            text = entity["text"]
            if text not in unique_entities or entity["confidence"] > unique_entities[text]["confidence"]:
                unique_entities[text] = entity
        
        entity_names = [e["text"] for e in unique_entities.values()]
        
        # 步骤3: 图检索
        graph_results = []
        subgraph_data = None
        
        if entity_names:
            # 对每个实体进行图搜索
            for entity_name in entity_names[:5]:  # 限制实体数量
                results = await self.graph_search(entity_name, limit=5)
                graph_results.extend(results)
            
            # 子图搜索（GraphRAG 高级功能）
            if len(entity_names) > 1:
                subgraph_data = await self.graph_subgraph_search(entity_names[:3], depth=2)
        
        # 步骤4: 结果融合和评分
        enhanced_results = self._merge_results(vector_results, graph_results, entity_names)
        
        return {
            "vector_results": vector_results,
            "graph_results": graph_results,
            "subgraph": subgraph_data,
            "entities": list(unique_entities.values()),
            "enhanced_context": enhanced_results,
            "query": query
        }
    
    def _merge_results(self, vector_results: List[Dict], graph_results: List[Dict], entities: List[str]) -> str:
        """
        融合向量和图检索结果，生成增强上下文
        
        这是 GraphRAG 的关键：将结构化图信息与文本信息结合
        """
        context_parts = []
        
        # 添加向量检索的文本内容
        if vector_results:
            context_parts.append("相关文本内容：")
            for i, result in enumerate(vector_results[:3], 1):
                text_id = result.get("text_id", "")
                score = result.get("score", 0)
                context_parts.append(f"{i}. {text_id} (相似度: {score:.2f})")
        
        # 添加图检索的关系信息
        if graph_results:
            context_parts.append("\n相关实体关系：")
            seen_relations = set()
            for result in graph_results[:5]:
                if 'a' in result and 'b' in result and 'rel_type' in result:
                    a_name = result['a'].get('name', '未知')
                    b_name = result['b'].get('name', '未知')
                    rel_type = result.get('rel_type', '相关')
                    relation_key = f"{a_name}-{rel_type}-{b_name}"
                    if relation_key not in seen_relations:
                        seen_relations.add(relation_key)
                        context_parts.append(f"- {a_name} {rel_type} {b_name}")
        
        # 添加识别的实体
        if entities:
            context_parts.append(f"\n识别到的实体：{', '.join(entities[:5])}")
        
        return "\n".join(context_parts)

# 全局 RAG 服务实例
rag_service = RAGService()

