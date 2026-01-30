"""
GraphRAG 检索服务
GraphRAG: 结合图数据库和向量检索的增强生成技术
"""
import logging
import re
import json
import asyncio
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer
from app.core.milvus_client import milvus_client
from app.core.neo4j_client import neo4j_client
from app.core.config import settings

logger = logging.getLogger(__name__)

def _strip_emoji(text: str) -> str:
    """去掉回复中所有表情符号，避免 TTS 异常或界面显示杂乱。"""
    if not text or not isinstance(text, str):
        return text or ""
    # 常见 emoji / 符号块（Misc Symbols, Dingbats, Emoticons, 以及补充平面表情等）
    s = re.sub(r"[\u2600-\u26FF\u2700-\u27BF\U0001F300-\U0001F9FF]", "", text)
    s = re.sub(r"\s{2,}", " ", s).strip()
    # 去掉末尾不可见/控制字符，避免 TTS 少读最后几个字
    s = re.sub(r"[\s\u200b\u200c\u200d\ufeff\r\n]+$", "", s)
    # 若末尾没有句号/问号/叹号，补句号，减少 TTS 截断
    if s and s[-1] not in "。！？.!?…":
        s = s.rstrip("，、；：") + "。"
    return s


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
        self.llm_client = None
        # Milvus 集合加载状态缓存：避免每次搜索都 load_state/load
        self._milvus_loaded_collections: set[str] = set()
        self._init_embedding_model()
        self._init_ner()
        self._init_llm_client()

    async def parse_scenic_text(self, text: str) -> Optional[Dict[str, Any]]:
        """
        将景区介绍类文本结构化为 JSON，供图数据库构建“一簇”使用。
        如果判断不是景区类文本，则返回 None。
        """
        # 简单启发式：包含这些关键词时才尝试解析，避免对所有知识都调用 LLM
        scenic_keywords = ["景区", "风景区", "旅游度假区", "景点", "度假区"]
        if not any(k in text for k in scenic_keywords):
            return None

        if not self.llm_client:
            return None

        system_prompt = """
你是景区知识结构化助手。请把一段中文景区介绍提取成 JSON，严格按字段返回，不要多余说明。

返回字段：
- scenic_spot: 景区名称（字符串）
- location: 行政层级数组，例如 ["四川省", "宜宾市", "长宁县"]（若缺少下级可省略）
- area: 面积（原文中的描述字符串，若没有则为 null）
- features: 特色数组，例如 ["天然竹林","森林覆盖率93%","气候温和","雨量充沛"]
- spots: 子景点数组，例如 ["竹海博物馆","花溪十三桥","海中海","古刹"]
- awards: 荣誉数组，例如 ["国家首批4A级旅游区","全国康养旅游基地","国家级旅游度假区"]

只输出 JSON 对象，不要解释。
"""
        try:
            resp = self.llm_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                temperature=0.1,
                max_tokens=512,
            )
            raw = resp.choices[0].message.content
            data = json.loads(raw)

            # 基本字段校验
            if not isinstance(data, dict):
                return None
            scenic_name = data.get("scenic_spot")
            if not scenic_name or not isinstance(scenic_name, str):
                return None

            # 规范化字段类型
            data["location"] = data.get("location") or []
            data["features"] = data.get("features") or []
            data["spots"] = data.get("spots") or []
            data["awards"] = data.get("awards") or []
            return data
        except Exception as e:
            logger.warning(f"parse_scenic_text failed: {e}")
            return None

    async def parse_attraction_text(self, name: str, text: str) -> Optional[Dict[str, Any]]:
        """
        将“单个景点”介绍结构化为 JSON，供图数据库构建“以景点为中心的一簇”使用。
        返回字段：
        - name: 景点名称
        - location: 行政层级数组，例如 ["四川省", "宜宾市", "长宁县"]（可为空）
        - features: 特色/要点数组
        - honors: 荣誉/称号数组
        - category: 类别（可为空）
        """
        if not name or not isinstance(name, str):
            return None
        if not self.llm_client:
            return None

        system_prompt = """
你是景点知识结构化助手。请把一段中文“单个景点”的介绍提取成 JSON，严格按字段返回，不要多余说明。

返回字段：
- name: 景点名称（字符串）
- location: 行政层级数组，例如 ["四川省", "宜宾市", "长宁县"]（若无法判断则返回 []）
- category: 类别（字符串或 null）
- features: 特色/要点数组（若没有则 []）
- honors: 荣誉/称号数组（若没有则 []）

只输出 JSON 对象，不要解释。
"""
        try:
            resp = self.llm_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"景点名称：{name}\n\n{text}"},
                ],
                temperature=0.1,
                max_tokens=512,
            )
            raw = resp.choices[0].message.content
            data = json.loads(raw)
            if not isinstance(data, dict):
                return None
            if data.get("name") and not isinstance(data.get("name"), str):
                return None
            data["name"] = (data.get("name") or name).strip()
            data["location"] = data.get("location") or []
            data["features"] = data.get("features") or []
            data["honors"] = data.get("honors") or []
            return data
        except Exception as e:
            logger.warning(f"parse_attraction_text failed: {e}")
            return None
    
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
    
    def _init_llm_client(self):
        """初始化LLM客户端（硅基流动/OpenAI）"""
        try:
            if settings.OPENAI_API_KEY:
                import openai
                # 配置OpenAI客户端
                client_kwargs = {
                    "api_key": settings.OPENAI_API_KEY
                }
                # 如果配置了硅基流动的API地址，使用它
                if settings.OPENAI_API_BASE:
                    client_kwargs["base_url"] = settings.OPENAI_API_BASE
                
                self.llm_client = openai.OpenAI(**client_kwargs)
                logger.info(f"LLM client initialized (base_url: {settings.OPENAI_API_BASE or 'default'})")
            else:
                logger.warning("OpenAI API key not configured, LLM generation disabled")
        except Exception as e:
            logger.error(f"Failed to initialize LLM client: {e}")
            self.llm_client = None
    
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

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """批量生成嵌入向量（比逐条 encode 更快）"""
        if not self.embedding_model:
            raise ValueError("Embedding model not loaded")
        if not texts:
            return []
        embs = self.embedding_model.encode(texts, convert_to_numpy=True)
        return embs.tolist()
    
    async def vector_search(self, query: str, collection_name: str = "tour_knowledge", top_k: int = 5) -> List[Dict[str, Any]]:
        """向量相似度搜索"""
        if not milvus_client.connected:
            milvus_client.connect()
        
        # 确保集合存在：首次使用/未上传知识库时，避免 SchemaNotReadyException
        try:
            collection = milvus_client.create_collection_if_not_exists(
                collection_name,
                dimension=384,  # 与 embedding 模型维度保持一致
                load=False  # 先不加载，后面统一处理
            )
        except Exception as e:
            # Milvus 未安装/未启动/不可用时，向量检索降级为空（GraphRAG 仍可继续走图检索/LLM）
            logger.warning(f"Milvus not available for vector search, fallback to empty results: {e}")
            return []
        
        # 检查集合是否存在
        try:
            from pymilvus import utility
            if not utility.has_collection(collection_name):
                logger.warning(f"Collection '{collection_name}' does not exist")
                return []
        except Exception as e:
            logger.warning(f"Failed to check collection existence: {e}")
            return []
        
        # 尽量避免每次请求都 load_state/load：用内存缓存 + 失败兜底
        if collection_name not in self._milvus_loaded_collections:
            try:
                from pymilvus import utility
                load_state = utility.load_state(collection_name)

                is_loaded = False
                if isinstance(load_state, dict):
                    state_value = (
                        load_state.get("state", "").upper()
                        if isinstance(load_state.get("state"), str)
                        else str(load_state.get("state", "")).upper()
                    )
                    is_loaded = state_value in ("LOADED", "LOADED_FOR_SEARCH")
                elif isinstance(load_state, str):
                    is_loaded = load_state.upper() in ("LOADED", "LOADED_FOR_SEARCH")
                else:
                    is_loaded = "LOADED" in str(load_state).upper()

                if not is_loaded:
                    logger.info(f"Collection '{collection_name}' is not loaded (state: {load_state}), loading now...")
                    collection.load()
                self._milvus_loaded_collections.add(collection_name)
            except Exception as e:
                logger.warning(f"Failed to ensure collection '{collection_name}' loaded, will rely on retry: {e}")
        
        # 生成查询向量
        query_vector = [self.generate_embedding(query)]
        
        # 搜索
        try:
            search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
            results = collection.search(
                data=query_vector,
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=["text_id"]
            )
        except Exception as e:
            # 如果搜索失败，可能是集合未加载，尝试重新加载后重试一次
            if "not loaded" in str(e).lower() or "collection not loaded" in str(e).lower():
                logger.warning(f"Search failed due to collection not loaded, retrying after reload: {e}")
                try:
                    collection.load()
                    self._milvus_loaded_collections.add(collection_name)
                    results = collection.search(
                        data=query_vector,
                        anns_field="embedding",
                        param=search_params,
                        limit=top_k,
                        output_fields=["text_id"]
                    )
                except Exception as retry_error:
                    logger.error(f"Retry search failed: {retry_error}")
                    return []
            else:
                logger.error(f"Search failed: {e}")
                return []
        
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
        # 关系类型无法参数化，只能做白名单/格式校验后再拼接，避免注入
        rel = None
        if relation_type and isinstance(relation_type, str):
            rel_candidate = relation_type.strip().upper()
            if re.match(r"^[A-Z_][A-Z0-9_]*$", rel_candidate):
                rel = rel_candidate

        if rel:
            query = f"""
            MATCH (a)-[r:{rel}]->(b)
            WHERE a.name CONTAINS $name OR b.name CONTAINS $name
            RETURN a, r, b, labels(a) as a_labels, labels(b) as b_labels, type(r) as rel_type
            LIMIT $limit
            """
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
        
        # 深度不能参数化到可变长度里（Neo4j 限制），但可以严格校验后插入整数；实体列表用参数化
        safe_depth = 2
        try:
            safe_depth = int(depth)
        except Exception:
            safe_depth = 2
        safe_depth = max(1, min(safe_depth, 3))

        query = f"""
        MATCH path = (a)-[*1..{safe_depth}]-(b)
        WHERE a.name IN $entities OR b.name IN $entities
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
        results = neo4j_client.execute_query(query, {"entities": entities})
        
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

    async def _build_scenic_attractions_context(
        self,
        query: str,
        rag_results: Dict[str, Any],
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        基于当前查询 + 图子图 + 对话上下文，补充“某个景区下有哪些景点”的结构化信息。
        场景：用户问“现在有哪些景点”“这个景区有哪些景点”等。
        """
        # 只在明显是“列举景点”的问题时触发，避免所有问句都扫图
        list_patterns = [
            r"有哪些景点",
            r"景点都有(什么|哪些)",
            r"景点情况",
            r"景点分布",
        ]
        if not any(re.search(p, query) for p in list_patterns):
            return ""

        scenic_names: set[str] = set()

        # 1) 优先从子图里找 ScenicSpot 节点
        subgraph = rag_results.get("subgraph") or {}
        for node in subgraph.get("nodes", []):
            labels = set(node.get("labels") or [])
            props = node.get("properties") or {}
            if "ScenicSpot" in labels and isinstance(props.get("name"), str):
                scenic_names.add(props["name"])

        # 2) 如果子图里没有，再从对话上下文里抽实体，去 Neo4j 里验证哪些是景区名
        if not scenic_names and conversation_history:
            # 只看最近几轮用户说的话
            recent_user_text = "。".join(
                msg["content"]
                for msg in conversation_history[-6:]
                if msg.get("role") == "user" and isinstance(msg.get("content"), str)
            )
            if recent_user_text:
                for ent in self.extract_entities(recent_user_text):
                    cand = ent.get("text")
                    if not cand or not isinstance(cand, str):
                        continue
                    # 去 Neo4j 里确认一下是否存在对应的 ScenicSpot
                    try:
                        check_q = """
                        MATCH (s:ScenicSpot {name: $name})
                        RETURN s.name AS name
                        LIMIT 1
                        """
                        res = neo4j_client.execute_query(check_q, {"name": cand})
                        if res and isinstance(res, list) and res[0].get("name"):
                            scenic_names.add(res[0]["name"])
                    except Exception:
                        continue

        # 3) 兜底：若仍未识别到任何景区（例如用户直接问“现在有哪些景点”且无历史），则查图中所有景区
        if not scenic_names:
            try:
                all_scenic_q = """
                MATCH (s:ScenicSpot) RETURN s.name AS name LIMIT 5
                """
                rows = neo4j_client.execute_query(all_scenic_q, {}) or []
                for row in rows:
                    nm = row.get("name")
                    if nm and isinstance(nm, str):
                        scenic_names.add(nm)
            except Exception as e:
                logger.warning(f"query all ScenicSpot names failed: {e}")

        if not scenic_names:
            return ""

        # 4) 针对识别到的每个景区，列出它下面的景点（HAS_SPOT 指向的 Spot/Attraction + 属于 该景区的 Attraction）
        parts: List[str] = []
        for scenic_name in list(scenic_names)[:3]:  # 最多 3 个景区，避免上下文过长
            try:
                cypher = """
                MATCH (s:ScenicSpot {name: $name})
                OPTIONAL MATCH (s)-[:HAS_SPOT]->(n)
                OPTIONAL MATCH (s)<-[:属于]-(a:Attraction)
                WITH s, collect(DISTINCT n) AS spot_list, collect(DISTINCT a) AS att_list
                UNWIND spot_list + att_list AS x
                WITH s, x WHERE x IS NOT NULL
                WITH DISTINCT s, x, coalesce(x.name, x.text_id) AS xname
                WHERE xname IS NOT NULL AND NOT (xname STARTS WITH 'kb_')
                RETURN s.name AS scenic_name, xname AS attraction_name
                ORDER BY attraction_name
                LIMIT 50
                """
                rows = neo4j_client.execute_query(cypher, {"name": scenic_name}) or []
            except Exception as e:
                logger.warning(f"query scenic attractions failed for '{scenic_name}': {e}")
                continue

            names: List[str] = []
            for row in rows:
                nm = row.get("attraction_name")
                if not nm or nm in names:
                    continue
                names.append(nm)

            if names:
                joined = "、".join(names)
                parts.append(f"根据图数据库，景区「{scenic_name}」下的相关景点包括：{joined}。")

        return "\n".join(parts)
    
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
    
    async def generate_answer(
        self, 
        query: str, 
        context: Optional[str] = None, 
        use_rag: bool = True,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        character_prompt: Optional[str] = None
    ) -> str:
        """
        使用LLM生成回答（支持硅基流动和多轮对话）
        
        Args:
            query: 用户查询
            context: 可选的上下文信息
            use_rag: 是否使用RAG检索增强
            conversation_history: 对话历史记录
            character_prompt: 角色提示词
        
        Returns:
            生成的回答
        """
        if not self.llm_client:
            return "抱歉，AI服务未配置，无法生成回答。"
        
        rag_debug: Optional[Dict[str, Any]] = None
        # 如果使用RAG，先进行检索
        if use_rag:
            rag_results = await self.hybrid_search(query, top_k=5)
            context = rag_results.get("enhanced_context", "") or ""

            # 基于当前查询 + 图结果 + 对话上下文，补充“当前景区有哪些景点”的结构化说明
            scenic_ctx = await self._build_scenic_attractions_context(
                query=query,
                rag_results=rag_results,
                conversation_history=conversation_history,
            )
            if scenic_ctx:
                context = f"{context}\n\n{scenic_ctx}" if context else scenic_ctx

            rag_debug = {
                "query": rag_results.get("query") or query,
                "vector_results": rag_results.get("vector_results", [])[:5],
                "graph_results": rag_results.get("graph_results", [])[:5],
                "subgraph": rag_results.get("subgraph"),
                "enhanced_context": context or "",
                "entities": rag_results.get("entities", []),
            }
        
        # 构建系统提示词
        base_system_prompt = """你是一个专业的景区AI导游助手。请根据提供的上下文信息，用友好、专业、准确的语言回答游客的问题。
回答要求：
1. 基于提供的上下文信息回答
2. 语言简洁明了，适合口语化表达
3. 如果信息不足，诚实说明
4. 不要编造信息
5. 不要透露任何内部标识符/编号/ID（例如 kb_***、text_id、session_id 等）；自我介绍时也不要输出任何“编号”"""
        
        # 如果有角色提示词，合并到系统提示词中
        if character_prompt:
            system_prompt = f"{base_system_prompt}\n\n角色设定：{character_prompt}"
        else:
            system_prompt = base_system_prompt
        
        # 构建消息列表
        messages = [{"role": "system", "content": system_prompt}]
        
        # 添加对话历史
        if conversation_history:
            messages.extend(conversation_history)
        
        # 添加当前查询和上下文
        user_prompt = f"""用户问题：{query}

上下文信息：
{context if context else "无额外上下文信息"}

请基于以上信息回答用户的问题。"""
        messages.append({"role": "user", "content": user_prompt})
        
        try:
            response = self.llm_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=1000
            )
            
            answer = response.choices[0].message.content
            # 安全清理：移除知识库内部 text_id / 编号，避免暴露 kb_*** 这类内部标识
            if answer:
                answer = re.sub(r"编号为\s*kb_\d+", "", answer)
                answer = re.sub(r"\bkb_\d+\b", "", answer)
                answer = re.sub(r"\s{2,}", " ", answer).strip()
            # 去掉所有表情符号，避免 TTS 异常或末尾不读
            if answer:
                answer = _strip_emoji(answer)
            # 将 RAG 检索结果 + 最终回答记录到日志文件，便于管理员在分析界面查看
            try:
                log_root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
                os.makedirs(log_root, exist_ok=True)
                log_path = os.path.join(log_root, "rag_context.log")
                entry = {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "query": query,
                    "character_prompt": character_prompt,
                    "use_rag": use_rag,
                    "rag_debug": rag_debug,
                    "final_answer_preview": answer[:400] if answer else "",
                }
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                # 只保留最近 5 条，避免日志文件无限增长
                try:
                    with open(log_path, "r", encoding="utf-8") as f:
                        lines = [ln for ln in f.readlines() if ln.strip()]
                    if len(lines) > 5:
                        with open(log_path, "w", encoding="utf-8") as f:
                            f.writelines(lines[-5:])
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"Failed to write RAG context log: {e}")

            logger.info(f"Generated answer for query: {query[:50]}...")
            return answer
            
        except Exception as e:
            logger.error(f"Failed to generate answer: {e}")
            return f"抱歉，生成回答时出现错误：{str(e)}"

# 全局 RAG 服务实例
rag_service = RAGService()

