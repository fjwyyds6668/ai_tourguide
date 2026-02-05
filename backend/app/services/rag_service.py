"""GraphRAG 检索服务：图数据库 + 向量检索增强生成"""
import logging
import re
import json
import asyncio
import os
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
from sentence_transformers import SentenceTransformer
from app.core.milvus_client import milvus_client
from app.core.neo4j_client import neo4j_client
from app.core.config import settings
from app.services.rag_settings import (
    RAG_RELEVANCE_SCORE_THRESHOLD,
    RAG_COLLECTION_NAME,
    RAG_EMBEDDING_MODEL_NAME,
    RAG_DEFAULT_TOP_K,
    EMBEDDING_CACHE_MAX_SIZE,
    VECTOR_SEARCH_CACHE_MAX_SIZE,
    EMBEDDING_CACHE_TTL_SECONDS,
    VECTOR_SEARCH_CACHE_TTL_SECONDS,
    CACHE_STATS_LOG_EVERY_N_CALLS,
    MILVUS_METRIC_TYPE,
    MILVUS_NPROBE,
)

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """查询意图类型"""
    ROUTE = "route"  # 路线/行程推荐
    LISTING = "listing"  # 列表/数量查询
    DETAIL = "detail"  # 详情/介绍查询
    COMPARISON = "comparison"  # 比较类查询
    LOCATION = "location"  # 位置/导航查询
    FEATURE = "feature"  # 特色/功能查询
    GENERAL = "general"  # 通用查询


def _monotonic() -> float:
    return time.monotonic()

def _strip_emoji(text: str) -> str:
    """去掉表情与末尾控制字符，避免 TTS 异常；缺句尾时补句号。"""
    if not text or not isinstance(text, str):
        return text or ""
    s = re.sub(
        r"[\u2600-\u26FF\u2700-\u27BF"
        r"\U0001F300-\U0001F9FF"
        r"\U0001FA00-\U0001FAFF"  # newer emoji blocks (e.g., 🫶)
        r"]",
        "",
        text,
    )
    s = re.sub(r"[~\uFF5E\u301C]", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    s = re.sub(r"[\s\u200b\u200c\u200d\ufeff\r\n]+$", "", s)
    if s and s[-1] not in "。！？.!?…":
        s = s.rstrip("，、；：") + "。"
    return s

def _clean_special_symbols(text: str) -> str:
    """清理特殊符号和 Markdown 格式，确保输出为纯文本"""
    if not text or not isinstance(text, str):
        return text or ""
    s = text
    # 移除 Markdown 粗体、斜体符号
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)  # **粗体** -> 粗体
    s = re.sub(r"\*([^*]+)\*", r"\1", s)  # *斜体* -> 斜体
    s = re.sub(r"#+\s*", "", s)  # Markdown 标题符号
    # 移除列表符号（保留内容）
    s = re.sub(r"^[\s]*[-•▪▫]\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"^[\s]*[1-9]\d*[\.、]\s+", "", s, flags=re.MULTILINE)  # 数字列表
    # 移除装饰性符号
    s = re.sub(r"[～~——…•▪▫]+", "", s)
    # 移除 emoji 数字（如 1️⃣、2️⃣）
    s = re.sub(r"[\u0030-\u0039]\uFE0F\u20E3", "", s)
    # 移除多余的装饰性标点
    s = re.sub(r"[。]{2,}", "。", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


try:
    import jieba
    import jieba.posseg as pseg
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False
    logger.warning("jieba not available, using simple keyword extraction")

class RAGService:
    """GraphRAG：实体识别 + Milvus 向量检索 + Neo4j 图检索 + 结果融合。"""

    def __init__(self):
        self.embedding_model = None
        self.llm_client = None
        self._milvus_loaded_collections: set[str] = set()
        self._embedding_cache: Dict[str, Tuple[List[float], float]] = {}
        self._vector_search_cache: Dict[
            Tuple[str, str, int], Tuple[List[Dict[str, Any]], float]
        ] = {}
        self._cache_stats: Dict[str, int] = {
            "embedding_calls": 0,
            "embedding_hits": 0,
            "embedding_misses": 0,
            "vector_calls": 0,
            "vector_hits": 0,
            "vector_misses": 0,
        }
        self._init_embedding_model()
        self._init_ner()
        self._init_llm_client()

    def _log_cache_stats_if_needed(self) -> None:
        every = max(1, int(CACHE_STATS_LOG_EVERY_N_CALLS))
        total = int(self._cache_stats.get("embedding_calls", 0)) + int(
            self._cache_stats.get("vector_calls", 0)
        )
        if total <= 0 or total % every != 0:
            return

        def _rate(hit: int, call: int) -> float:
            return (hit / call) if call > 0 else 0.0

        e_calls = int(self._cache_stats.get("embedding_calls", 0))
        v_calls = int(self._cache_stats.get("vector_calls", 0))
        logger.info(
            "cache_stats: embedding_hit_rate=%.1f%% (%d/%d), vector_hit_rate=%.1f%% (%d/%d), sizes: embedding=%d, vector=%d",
            _rate(int(self._cache_stats.get("embedding_hits", 0)), e_calls) * 100,
            int(self._cache_stats.get("embedding_hits", 0)),
            e_calls,
            _rate(int(self._cache_stats.get("vector_hits", 0)), v_calls) * 100,
            int(self._cache_stats.get("vector_hits", 0)),
            v_calls,
            len(self._embedding_cache),
            len(self._vector_search_cache),
        )

    def _cache_get_embedding(self, key: str) -> Optional[List[float]]:
        item = self._embedding_cache.get(key)
        if not item:
            return None
        payload, expires_at = item
        if expires_at > 0 and _monotonic() >= expires_at:
            self._embedding_cache.pop(key, None)
            return None
        return payload

    def _cache_set_embedding(self, key: str, payload: List[float]) -> None:
        ttl = max(0, int(EMBEDDING_CACHE_TTL_SECONDS))
        expires_at = _monotonic() + ttl if ttl > 0 else 0.0
        if len(self._embedding_cache) >= EMBEDDING_CACHE_MAX_SIZE:
            try:
                first_key = next(iter(self._embedding_cache))
                self._embedding_cache.pop(first_key, None)
            except StopIteration:
                pass
        self._embedding_cache[key] = (payload, expires_at)

    def _cache_get_vector(
        self, key: Tuple[str, str, int]
    ) -> Optional[List[Dict[str, Any]]]:
        item = self._vector_search_cache.get(key)
        if not item:
            return None
        payload, expires_at = item
        if expires_at > 0 and _monotonic() >= expires_at:
            self._vector_search_cache.pop(key, None)
            return None
        return payload

    def _cache_set_vector(
        self, key: Tuple[str, str, int], payload: List[Dict[str, Any]]
    ) -> None:
        ttl = max(0, int(VECTOR_SEARCH_CACHE_TTL_SECONDS))
        expires_at = _monotonic() + ttl if ttl > 0 else 0.0
        if len(self._vector_search_cache) >= VECTOR_SEARCH_CACHE_MAX_SIZE:
            try:
                first_key = next(iter(self._vector_search_cache))
                self._vector_search_cache.pop(first_key, None)
            except StopIteration:
                pass
        self._vector_search_cache[key] = (payload, expires_at)

    async def parse_scenic_text(self, text: str) -> Optional[Dict[str, Any]]:
        """将景区介绍结构化为 JSON 供图库建簇；非景区类返回 None。"""
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
            if not isinstance(data, dict):
                return None
            scenic_name = data.get("scenic_spot")
            if not scenic_name or not isinstance(scenic_name, str):
                return None
            data["location"] = data.get("location") or []
            data["features"] = data.get("features") or []
            data["spots"] = data.get("spots") or []
            data["awards"] = data.get("awards") or []
            return data
        except Exception as e:
            logger.warning(f"parse_scenic_text failed: {e}")
            return None

    async def parse_attraction_text(self, name: str, text: str) -> Optional[Dict[str, Any]]:
        """将单景点介绍结构化为 JSON 供图库建簇。"""
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
        try:
            self.embedding_model = SentenceTransformer(RAG_EMBEDDING_MODEL_NAME)
            logger.info("Embedding model loaded: %s", RAG_EMBEDDING_MODEL_NAME)
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            self.embedding_model = None
    
    def _init_ner(self):
        if JIEBA_AVAILABLE:
            try:
                jieba.initialize()
                logger.info("NER model (jieba) initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize jieba: {e}")
    
    def _init_llm_client(self):
        try:
            if settings.OPENAI_API_KEY:
                import openai
                client_kwargs = {"api_key": settings.OPENAI_API_KEY}
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
        """从文本提取实体，返回 [{"text", "type", "confidence"}]。"""
        stop_words = {"这里", "那里", "哪些", "什么", "这个", "那个", "景点", "景区", "地方", 
                      "attraction", "scenic", "spot", "这里有哪些", "有哪些景点", "景点都有"}
        entities = []
        if JIEBA_AVAILABLE:
            words = pseg.cut(text)
            for word, flag in words:
                if word in stop_words:
                    continue
                if (flag in ['ns', 'nr', 'nt', 'nz'] or len(word) >= 3) and len(word) >= 2:
                    entities.append({
                        "text": word,
                        "type": self._map_pos_to_entity_type(flag),
                        "confidence": 0.8
                    })
        else:
            pattern = r'[\u4e00-\u9fa5]{2,}'
            matches = re.finditer(pattern, text)
            for match in matches:
                word = match.group()
                if word not in stop_words:
                    entities.append({
                        "text": word,
                        "type": "KEYWORD",
                        "confidence": 0.6
                    })
        seen = set()
        unique_entities = []
        for entity in entities:
            if entity["text"] not in seen:
                seen.add(entity["text"])
                unique_entities.append(entity)
        
        return unique_entities
    
    def _map_pos_to_entity_type(self, pos: str) -> str:
        mapping = {
            'ns': 'LOCATION', 'nr': 'PERSON', 'nt': 'ORG', 'nz': 'OTHER',
        }
        return mapping.get(pos, 'KEYWORD')
    
    def generate_embedding(self, text: str) -> List[float]:
        """生成文本嵌入向量"""
        if not self.embedding_model:
            raise ValueError("Embedding model not loaded")

        key = (text or "").strip()
        if not key:
            return []
        self._cache_stats["embedding_calls"] = int(self._cache_stats.get("embedding_calls", 0)) + 1
        cached = self._cache_get_embedding(key)
        if cached is not None:
            self._cache_stats["embedding_hits"] = int(self._cache_stats.get("embedding_hits", 0)) + 1
            self._log_cache_stats_if_needed()
            return cached
        self._cache_stats["embedding_misses"] = int(self._cache_stats.get("embedding_misses", 0)) + 1

        embedding = self.embedding_model.encode(key, convert_to_numpy=True)
        emb_list = embedding.tolist()
        self._cache_set_embedding(key, emb_list)
        self._log_cache_stats_if_needed()
        return emb_list

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """批量生成嵌入向量（比逐条 encode 更快）"""
        if not self.embedding_model:
            raise ValueError("Embedding model not loaded")
        if not texts:
            return []

        keys = [(t or "").strip() for t in texts]
        results: List[List[float]] = []
        to_encode: List[str] = []
        missing_indices: List[int] = []
        for idx, key in enumerate(keys):
            if not key:
                results.append([])
                continue
            self._cache_stats["embedding_calls"] = int(self._cache_stats.get("embedding_calls", 0)) + 1
            cached = self._cache_get_embedding(key)
            if cached is not None:
                self._cache_stats["embedding_hits"] = int(self._cache_stats.get("embedding_hits", 0)) + 1
                results.append(cached)
            else:
                self._cache_stats["embedding_misses"] = int(self._cache_stats.get("embedding_misses", 0)) + 1
                missing_indices.append(idx)
                to_encode.append(key)
                results.append([])  # 占位，后面填充

        if to_encode:
            embs = self.embedding_model.encode(to_encode, convert_to_numpy=True).tolist()
            for pos, emb in zip(missing_indices, embs):
                key = keys[pos]
                self._cache_set_embedding(key, emb)
                results[pos] = emb

        self._log_cache_stats_if_needed()
        return results
    
    async def vector_search(
        self,
        query: str,
        collection_name: str = "",
        top_k: int = 0,
    ) -> List[Dict[str, Any]]:
        """向量相似度搜索。"""
        collection_name = (collection_name or RAG_COLLECTION_NAME).strip()
        top_k = int(top_k or RAG_DEFAULT_TOP_K)
        if not query or not collection_name or top_k <= 0:
            return []

        cache_key = (query, collection_name, top_k)
        self._cache_stats["vector_calls"] = int(self._cache_stats.get("vector_calls", 0)) + 1
        cached = self._cache_get_vector(cache_key)
        if cached is not None:
            self._cache_stats["vector_hits"] = int(self._cache_stats.get("vector_hits", 0)) + 1
            self._log_cache_stats_if_needed()
            logger.debug(
                "vector_search cache hit: collection=%s, top_k=%d", collection_name, top_k
            )
            return [dict(item) for item in cached]
        self._cache_stats["vector_misses"] = int(self._cache_stats.get("vector_misses", 0)) + 1

        start_time = datetime.utcnow()
        if not milvus_client.connected:
            milvus_client.connect()
        try:
            collection = milvus_client.create_collection_if_not_exists(
                collection_name, dimension=384, load=False
            )
        except Exception as e:
            logger.warning(
                "Milvus not available for vector search, fallback to empty results: %s",
                e,
            )
            return []
        try:
            from pymilvus import utility
            if not utility.has_collection(collection_name):
                logger.warning(f"Collection '{collection_name}' does not exist")
                return []
        except Exception as e:
            logger.warning("Failed to check collection existence: %s", e)
            return []
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
                    logger.info(
                        "Collection '%s' is not loaded (state: %s), loading now...",
                        collection_name,
                        load_state,
                    )
                    collection.load()
                self._milvus_loaded_collections.add(collection_name)
            except Exception as e:
                logger.warning(
                    "Failed to ensure collection '%s' loaded, will rely on retry: %s",
                    collection_name,
                    e,
                )
        query_vector = [self.generate_embedding(query)]
        try:
            search_params = {
                "metric_type": str(MILVUS_METRIC_TYPE or "L2"),
                "params": {"nprobe": int(MILVUS_NPROBE or 10)},
            }
            results = collection.search(
                data=query_vector,
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=["text_id"]
            )
        except Exception as e:
            if "not loaded" in str(e).lower() or "collection not loaded" in str(e).lower():
                logger.warning(
                    "Search failed due to collection not loaded, retrying after reload: %s",
                    e,
                )
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
                    logger.error("Retry search failed: %s", retry_error)
                    return []
            else:
                logger.error("Search failed: %s", e)
                return []
        search_results = []
        if results and len(results) > 0:
            for hit in results[0]:
                search_results.append({
                    "id": hit.id,
                    "text_id": hit.entity.get("text_id", ""),
                    "distance": hit.distance,
                    "score": 1 / (1 + hit.distance) if hit.distance > 0 else 1.0,
                })
        
        elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        logger.info(
            "vector_search done: collection=%s, top_k=%d, hits=%d, elapsed=%.1fms",
            collection_name,
            top_k,
            len(search_results),
            elapsed_ms,
        )

        self._cache_set_vector(cache_key, [dict(item) for item in search_results])
        self._log_cache_stats_if_needed()

        return search_results
    
    async def graph_search(self, entity_name: str, relation_type: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """图数据库关系查询。relation_type 白名单校验后拼接，避免注入（异步，不阻塞事件循环）。"""
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
        
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            neo4j_client.execute_query,
            query,
            {"name": entity_name, "limit": limit}
        )
        
        return results or []

    async def _graph_search_many(
        self, entity_names: List[str], relation_type: str = None, per_entity_limit: int = 5
    ) -> List[Dict[str, Any]]:
        """批量图关系查询：把多次 graph_search 合并为一次 Neo4j 查询，减少 round-trip。"""
        names = [str(x).strip() for x in (entity_names or []) if str(x).strip()]
        if not names:
            return []
        names = names[:10]

        rel = None
        if relation_type and isinstance(relation_type, str):
            rel_candidate = relation_type.strip().upper()
            if re.match(r"^[A-Z_][A-Z0-9_]*$", rel_candidate):
                rel = rel_candidate

        per_limit = max(1, min(int(per_entity_limit or 5), 20))
        if rel:
            query = f"""
            UNWIND $names AS name
            CALL {{
              WITH name
              MATCH (a)-[r:{rel}]->(b)
              WHERE a.name CONTAINS name OR b.name CONTAINS name
              RETURN a, r, b, labels(a) as a_labels, labels(b) as b_labels, type(r) as rel_type
              LIMIT $per_limit
            }}
            RETURN name as query_name, a, r, b, a_labels, b_labels, rel_type
            """
        else:
            query = """
            UNWIND $names AS name
            CALL {
              WITH name
              MATCH (a)-[r]->(b)
              WHERE a.name CONTAINS name OR b.name CONTAINS name
              RETURN a, r, b, labels(a) as a_labels, labels(b) as b_labels, type(r) as rel_type
              LIMIT $per_limit
            }
            RETURN name as query_name, a, r, b, a_labels, b_labels, rel_type
            """

        loop = asyncio.get_event_loop()
        try:
            rows = await loop.run_in_executor(
                None,
                neo4j_client.execute_query,
                query,
                {"names": names, "per_limit": per_limit},
            )
            return rows or []
        except Exception as e:
            logger.warning("_graph_search_many failed: %s", e)
            return []
    
    async def graph_subgraph_search(self, entities: List[str], depth: int = 2) -> Dict[str, Any]:
        """基于多实体构建子图。depth 经校验后拼接（Neo4j 限制）。"""
        if not entities:
            return {"nodes": [], "relationships": []}
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
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            neo4j_client.execute_query,
            query,
            {"entities": entities}
        )
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
    
    def _query_needs_context(self, query: str) -> bool:
        """寒暄/致谢/告别/能力询问等返回 False，不检索；景区/景点问题才走 RAG。"""
        if not query or not isinstance(query, str):
            return False
        q = query.strip()
        if len(q) <= 1:
            return False
        no_context_patterns = [
            r"^(你好|您好|嗨|hello|hi|在吗|在不在)\s*[？?]?$",
            r"^(谢谢|感谢|多谢|谢谢您)\s*[！!。.]?$",
            r"^(再见|拜拜|bye)\s*[！!。.]?$",
            r"^(你是谁|你能做什么|有什么功能|你能干嘛|介绍下自己)\s*[？?]?$",
            r"^(帮助|help|怎么用|如何使用)\s*[？?]?$",
            r"^随便(问问|问问看)?\s*[？?]?$",
        ]
        for pat in no_context_patterns:
            if re.search(pat, q, re.IGNORECASE):
                return False
        return True
    
    def _is_listing_query(self, query: str) -> bool:
        """判断是否为“景点列表/数量”类问题，例如有哪些景点、景点分布、多少个景点等。"""
        if not query or not isinstance(query, str):
            return False
        q = query.strip()
        if not q:
            return False
        pattern = (
            r"有哪些景点|景点都有(什么|哪些)|景点情况|景点分布|有什么景点|景点.*有哪些"
            r"|有多少个?景点|多少个景点|景点有多少个?|景区有多少个?景点|几个景点"
        )
        return bool(re.search(pattern, q))

    def _is_route_query(self, query: str) -> bool:
        """判断是否为“路线/行程/推荐路线”类问题，需要多景点串联回答。"""
        if not query or not isinstance(query, str):
            return False
        q = query.strip()
        if not q:
            return False
        pattern = (
            r"路线|行程|推荐.*(路线|怎么走|游玩顺序)|(亲子|一日游|半日|游览).*路线"
            r"|怎么走|游玩路线|游览路线|逛.*顺序|先去.*再去|路线推荐|走法"
        )
        return bool(re.search(pattern, q))

    def _classify_query_intent(self, query: str) -> QueryIntent:
        """智能分类查询意图，返回对应的检索策略类型。"""
        if not query or not isinstance(query, str):
            return QueryIntent.GENERAL
        q = query.strip().lower()
        if not q:
            return QueryIntent.GENERAL
        
        # 路线/行程类（优先级最高，因为需要特殊处理）
        if re.search(
            r"路线|行程|推荐.*(路线|怎么走|游玩顺序)|(亲子|一日游|半日|游览).*路线"
            r"|怎么走|游玩路线|游览路线|逛.*顺序|先去.*再去|路线推荐|走法|游览顺序",
            q
        ):
            return QueryIntent.ROUTE
        
        # 列表/数量类
        if re.search(
            r"有哪些|都有(什么|哪些)|情况|分布|有什么|.*有哪些"
            r"|有多少个?|多少个|有多少|几个|列举|列出",
            q
        ):
            return QueryIntent.LISTING
        
        # 比较类
        if re.search(
            r"哪个(更好|更|比较|区别|不同)|对比|比较|区别|差异|哪个好|哪个更",
            q
        ):
            return QueryIntent.COMPARISON
        
        # 位置/导航类
        if re.search(
            r"在哪|位置|地址|怎么去|怎么到|导航|距离|多远|附近|周围",
            q
        ):
            return QueryIntent.LOCATION
        
        # 特色/功能类
        if re.search(
            r"特色|特点|好玩|有什么好玩的|有什么|功能|亮点|推荐理由|为什么|值得",
            q
        ):
            return QueryIntent.FEATURE
        
        # 详情/介绍类（包含具体景点名或"介绍"）
        if re.search(
            r"介绍|详情|详细|是什么|什么样|描述|说说|讲讲|了解",
            q
        ):
            return QueryIntent.DETAIL
        
        return QueryIntent.GENERAL

    def _get_search_strategy(self, intent: QueryIntent) -> Dict[str, Any]:
        """根据意图返回检索策略配置（top_k, 阈值, 图查询深度等）。"""
        strategies = {
            QueryIntent.ROUTE: {
                "top_k": 10,  # 路线需要更多候选
                "relevance_threshold": 0.1,  # 降低阈值，允许更多相关结果
                "graph_depth": 3,  # 深度图查询，找更多关联
                "expand_scenic_attractions": True,  # 扩展同景区多景点
                "max_attractions": 15,  # 最多15个景点供路线串联
                "force_at_least_one": True,  # 即使低分也保留至少一个
            },
            QueryIntent.LISTING: {
                "top_k": 8,
                "relevance_threshold": 0.15,
                "graph_depth": 2,
                "expand_scenic_attractions": True,
                "max_attractions": 30,  # 列表需要更多景点
                "force_at_least_one": True,
            },
            QueryIntent.DETAIL: {
                "top_k": 3,  # 详情查询精准即可
                "relevance_threshold": 0.3,  # 提高阈值，只要高相关
                "graph_depth": 1,  # 浅查询，只查直接关系
                "expand_scenic_attractions": False,  # 不扩展，专注单点
                "max_attractions": 1,
                "force_at_least_one": False,
            },
            QueryIntent.COMPARISON: {
                "top_k": 8,  # 比较需要多个实体
                "relevance_threshold": 0.2,
                "graph_depth": 2,
                "expand_scenic_attractions": False,
                "max_attractions": 5,  # 比较类限制数量
                "force_at_least_one": True,
            },
            QueryIntent.LOCATION: {
                "top_k": 5,
                "relevance_threshold": 0.2,
                "graph_depth": 2,  # 查位置关系
                "expand_scenic_attractions": False,
                "max_attractions": 1,
                "force_at_least_one": True,
            },
            QueryIntent.FEATURE: {
                "top_k": 6,
                "relevance_threshold": 0.2,
                "graph_depth": 2,  # 查特色/属性关系
                "expand_scenic_attractions": False,
                "max_attractions": 3,
                "force_at_least_one": True,
            },
            QueryIntent.GENERAL: {
                "top_k": 5,  # 默认值
                "relevance_threshold": RAG_RELEVANCE_SCORE_THRESHOLD,
                "graph_depth": 2,
                "expand_scenic_attractions": False,
                "max_attractions": 1,
                "force_at_least_one": True,
            },
        }
        return strategies.get(intent, strategies[QueryIntent.GENERAL])

    async def _get_scenic_spot_by_attraction_id(self, attraction_id: int) -> Optional[Dict[str, Any]]:
        """通过景点 id 反查所属景区，返回 {'sid', 's_name'} 或 None（异步，不阻塞事件循环）。"""
        try:
            query = """
            MATCH (a:Attraction {id: $aid})
            OPTIONAL MATCH (a)-[:属于]->(s1:ScenicSpot)
            OPTIONAL MATCH (s2:ScenicSpot)-[:HAS_SPOT]->(a)
            WITH a, coalesce(s1, s2) AS s WHERE s IS NOT NULL
            RETURN s.scenic_spot_id AS sid, s.name AS s_name
            LIMIT 1
            """
            loop = asyncio.get_event_loop()
            rows = await loop.run_in_executor(
                None,
                neo4j_client.execute_query,
                query,
                {"aid": int(attraction_id)}
            )
            if rows:
                row0 = rows[0]
                return {
                    "sid": row0.get("sid"),
                    "s_name": row0.get("s_name"),
                }
        except Exception as e:
            logger.warning(f"_get_scenic_spot_by_attraction_id failed attraction_id={attraction_id}: {e}")
        return None

    async def _get_scenic_attractions_sentence_by_name(self, scenic_name: str) -> str:
        """根据景区名称查询其下相关景点，并格式化为一句话描述（带数量信息，异步）。"""
        scenic_name = (scenic_name or "").strip()
        if not scenic_name:
            return ""
        try:
            scenic_attractions_q = """
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
            loop = asyncio.get_event_loop()
            rows = await loop.run_in_executor(
                None,
                neo4j_client.execute_query,
                scenic_attractions_q,
                {"name": scenic_name}
            ) or []
        except Exception as e:
            logger.warning(f"_get_scenic_attractions_sentence_by_name query failed scenic_name={scenic_name}: {e}")
            return ""

        attraction_names: List[str] = []
        for row in rows:
            nm = row.get("attraction_name")
            if not nm or nm in attraction_names:
                continue
            attraction_names.append(nm)
        if not attraction_names:
            return ""
        count = len(attraction_names)
        joined = "、".join(attraction_names)
        return f"根据图数据库，景区「{scenic_name}」下的相关景点共有 {count} 个，包括：{joined}。"

    async def hybrid_search(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """
        意图驱动的混合检索：向量检索 + 实体识别 + 图检索 + 结果融合。
        根据查询意图自动选择最优检索策略（top_k、阈值、图查询深度等）。
        """
        # 1. 意图分类
        intent = self._classify_query_intent(query)
        strategy = self._get_search_strategy(intent)
        
        # 使用策略中的 top_k（如果外部传入的 top_k 不是默认值，则优先使用外部值）
        effective_top_k = top_k if top_k != 5 else strategy["top_k"]
        effective_threshold = strategy["relevance_threshold"]
        graph_depth = strategy["graph_depth"]
        
        logger.debug(f"查询意图: {intent.value}, top_k={effective_top_k}, threshold={effective_threshold}, graph_depth={graph_depth}")
        
        errors: Dict[str, str] = {}
        try:
            vector_results = await self.vector_search(query, top_k=effective_top_k)
        except Exception as e:
            errors["milvus"] = str(e)
            logger.warning("hybrid_search vector_search failed (fallback to empty): %s", e)
            vector_results = []
        
        # 使用策略中的阈值过滤
        vector_results_relevant = [
            r
            for r in (vector_results or [])
            if (r.get("score") or 0) >= effective_threshold
        ]
        # 根据策略决定是否强制保留至少一个结果
        if not vector_results_relevant and vector_results and strategy.get("force_at_least_one", True):
            vector_results_relevant = vector_results[:1]
        vector_results = vector_results_relevant

        texts_to_extract = [query]
        if vector_results:
            text_ids = [
                r.get("text_id", "")
                for r in vector_results[:3]
                if r.get("text_id")
                and not (r.get("text_id", "").strip().startswith("kb_") or r.get("text_id", "").strip().startswith("attraction_"))
            ]
            texts_to_extract.extend(text_ids)
        
        if len(texts_to_extract) > 1:
            loop = asyncio.get_event_loop()
            entities_list = await asyncio.gather(*[
                loop.run_in_executor(None, self.extract_entities, text)
                for text in texts_to_extract
            ])
            entities = []
            for ent_list in entities_list:
                entities.extend(ent_list)
        else:
            entities = self.extract_entities(query)
        
        unique_entities = {}
        for entity in entities:
            text = entity["text"]
            if text not in unique_entities or entity["confidence"] > unique_entities[text]["confidence"]:
                unique_entities[text] = entity
        
        entity_names = [e["text"] for e in unique_entities.values()]
        
        text_ids_to_fetch = [
            (r.get("text_id") or "").strip()
            for r in (vector_results or [])
            if (r.get("text_id") or "").strip() and not (r.get("text_id") or "").strip().startswith("attraction_")
        ]
        
        graph_results: List[Dict[str, Any]] = []
        subgraph_data = None
        if entity_names:
            # 根据意图调整图查询参数
            per_entity_limit = 8 if intent == QueryIntent.ROUTE else 5
            tasks = [
                self._graph_search_many(entity_names[:5], per_entity_limit=per_entity_limit),
            ]
            # 根据策略中的 graph_depth 决定是否进行子图查询
            if len(entity_names) > 1 and graph_depth > 1:
                tasks.append(self.graph_subgraph_search(entity_names[:3], depth=graph_depth))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            if results:
                r0 = results[0]
                if not isinstance(r0, Exception):
                    graph_results = r0 or []
                elif isinstance(r0, Exception):
                    errors["neo4j_graph"] = str(r0)
            if len(tasks) > 1 and len(results) > 1:
                r1 = results[1]
                if not isinstance(r1, Exception):
                    subgraph_data = r1
                else:
                    errors["neo4j_subgraph"] = str(r1)
        text_contents = {}
        if text_ids_to_fetch:
            loop = asyncio.get_event_loop()
            try:
                text_contents = await loop.run_in_executor(
                    None,
                    self._get_text_contents_from_neo4j,
                    text_ids_to_fetch,
                )
            except Exception as e:
                errors["neo4j_text"] = str(e)
                logger.warning("hybrid_search fetch text contents failed: %s", e)
                text_contents = {}
        
        for r in vector_results or []:
            tid = (r.get("text_id") or "").strip()
            if tid and tid in text_contents:
                r["content"] = text_contents[tid]
        enhanced_results = self._merge_results(vector_results, graph_results, entity_names)
        attraction_ids = []
        primary_attraction_id = None
        for r in (vector_results or []):
            text_id = (r.get("text_id") or "").strip()
            if text_id.startswith("attraction_"):
                try:
                    aid = int(text_id.replace("attraction_", ""))
                    attraction_ids.append(aid)
                    if primary_attraction_id is None:
                        primary_attraction_id = aid
                except ValueError:
                    pass
        
        # 根据策略决定是否扩展同景区多景点
        should_expand = strategy.get("expand_scenic_attractions", False)
        max_attractions = strategy.get("max_attractions", 1)
        
        if should_expand and primary_attraction_id is not None:
            try:
                parent_info = await self._get_scenic_spot_by_attraction_id(primary_attraction_id)
                if parent_info:
                    s_name = parent_info.get("s_name")
                    if s_name:
                        # 合并查询：一次获取景点列表和 ID，避免两次 Neo4j 往返
                        async def fetch_scenic_attractions():
                            scenic_aids_q = """
                            MATCH (s:ScenicSpot {name: $name})
                            OPTIONAL MATCH (s)<-[:属于]-(a:Attraction)
                            OPTIONAL MATCH (s)-[:HAS_SPOT]->(a2:Attraction)
                            WITH collect(DISTINCT a) + collect(DISTINCT a2) AS xs
                            UNWIND xs AS x
                            WITH DISTINCT x WHERE x IS NOT NULL AND x.id IS NOT NULL
                            RETURN x.id AS aid, x.name AS name
                            ORDER BY aid
                            LIMIT 200
                            """
                            loop = asyncio.get_event_loop()
                            rows = await loop.run_in_executor(
                                None,
                                neo4j_client.execute_query,
                                scenic_aids_q,
                                {"name": str(s_name).strip()}
                            ) or []
                            aids: List[int] = []
                            names: List[str] = []
                            for rr in rows:
                                if rr and rr.get("aid") is not None:
                                    try:
                                        aids.append(int(rr["aid"]))
                                        if rr.get("name"):
                                            names.append(str(rr["name"]))
                                    except Exception:
                                        continue
                            return aids, names
                        
                        scenic_aids, attraction_names = await fetch_scenic_attractions()
                        
                        # 生成句子描述（如果还没有）
                        if attraction_names and "根据图数据库，景区「" not in (enhanced_results or ""):
                            count = len(attraction_names)
                            joined = "、".join(attraction_names[:20])  # 最多显示20个
                            sentence = f"根据图数据库，景区「{s_name}」下的相关景点共有 {count} 个，包括：{joined}。"
                            enhanced_results = sentence + "\n\n" + (enhanced_results or "")
                        
                        if scenic_aids:
                            # 使用策略中的 max_attractions
                            clusters_ctx = await self._get_attraction_cluster_context(scenic_aids, max_items=max_attractions)
                            if clusters_ctx:
                                # 根据意图添加不同的标题
                                if intent == QueryIntent.ROUTE:
                                    enhanced_results = (enhanced_results or "") + "\n\n【路线可选景点】\n" + clusters_ctx
                                else:
                                    enhanced_results = (enhanced_results or "") + "\n\n" + clusters_ctx
            except Exception as e:
                logger.warning(f"扩展景区景点失败 (intent={intent.value}): {e}")
        # 列举类问题（如「这个景区有多少景点」）若向量未命中 attraction_XX，则无 primary_attraction_id，
        # 此处兜底：从图库查所有景区，补充至少一个景区的景点数量，避免「查不到」。
        if intent == QueryIntent.LISTING and "根据图数据库，景区「" not in (enhanced_results or ""):
            try:
                async def fetch_first_scenic_listing():
                    all_scenic_q = """
                    MATCH (s:ScenicSpot) RETURN s.name AS name LIMIT 5
                    """
                    loop = asyncio.get_event_loop()
                    rows = await loop.run_in_executor(
                        None,
                        neo4j_client.execute_query,
                        all_scenic_q,
                        {}
                    ) or []
                    for row in rows:
                        nm = (row.get("name") or "").strip() if row else ""
                        if not nm:
                            continue
                        sentence = await self._get_scenic_attractions_sentence_by_name(nm)
                        if sentence:
                            return sentence
                    return None
                
                sentence = await fetch_first_scenic_listing()
                if sentence:
                    enhanced_results = (sentence + "\n\n" + (enhanced_results or "")).strip()
            except Exception as e:
                logger.warning(f"列举查询兜底查景区景点数量失败: {e}")
        query_about_scenic = bool(re.search(r"什么景区|哪个景区|是啥景区|这是什么景区|是哪个景区|啥景区|哪个景点.*景区|介绍.*景区|景区.*介绍|这个景区", (query or "").strip()))
        scenic_ctx_found = False
        if query_about_scenic:
            scenic_tasks = []
            if primary_attraction_id is not None:
                async def get_scenic_from_attraction():
                    try:
                        parent_info = await self._get_scenic_spot_by_attraction_id(primary_attraction_id)
                        if parent_info:
                            sid = parent_info.get("sid")
                            s_name = parent_info.get("s_name")
                            if sid is not None:
                                return await self._get_scenic_spot_cluster_context(int(sid))
                            if s_name:
                                return await self._get_scenic_spot_cluster_context_by_name(str(s_name).strip())
                    except Exception as e:
                        logger.warning(f"查询景点所属景区失败: {e}")
                    return ""
                scenic_tasks.append(get_scenic_from_attraction())
            
            if entity_names:
                async def get_scenic_from_entity(name):
                    try:
                        scenic_check_q = """
                        MATCH (s:ScenicSpot {name: $name})
                        RETURN s.scenic_spot_id AS sid, s.name AS s_name
                        LIMIT 1
                        """
                        loop = asyncio.get_event_loop()
                        scenic_rows = await loop.run_in_executor(
                            None,
                            neo4j_client.execute_query,
                            scenic_check_q,
                            {"name": name}
                        )
                        if scenic_rows:
                            row0 = scenic_rows[0]
                            sid = row0.get("sid")
                            s_name = row0.get("s_name")
                            if sid is not None:
                                return await self._get_scenic_spot_cluster_context(int(sid))
                            if s_name:
                                return await self._get_scenic_spot_cluster_context_by_name(str(s_name).strip())
                    except Exception as e:
                        logger.warning(f"从实体名称查找景区失败: {e}")
                    return ""
                for entity_name in entity_names[:3]:
                    scenic_tasks.append(get_scenic_from_entity(entity_name))
            
            if subgraph_data:
                async def get_scenic_from_subgraph():
                    for node in subgraph_data.get("nodes", []):
                        labels = set(node.get("labels") or [])
                        props = node.get("properties") or {}
                        if "ScenicSpot" in labels and isinstance(props.get("name"), str):
                            scenic_name = props["name"]
                            try:
                                return await self._get_scenic_spot_cluster_context_by_name(scenic_name)
                            except Exception as e:
                                logger.warning(f"从子图查找景区失败: {e}")
                                continue
                    return ""
                scenic_tasks.append(get_scenic_from_subgraph())
            
            if scenic_tasks:
                scenic_results = await asyncio.gather(*scenic_tasks, return_exceptions=True)
                for scenic_ctx in scenic_results:
                    if scenic_ctx and not isinstance(scenic_ctx, Exception) and scenic_ctx.strip():
                        enhanced_results = scenic_ctx + "\n\n" + (enhanced_results or "")
                        scenic_ctx_found = True
                        break
        # 非扩展类意图且未扩展时，添加单景点簇信息
        if (not should_expand) and primary_attraction_id is not None and not (query_about_scenic and scenic_ctx_found):
            cluster_ctx = await self._get_attraction_cluster_context([primary_attraction_id], max_items=1)
            if cluster_ctx:
                enhanced_results = (enhanced_results or "") + "\n\n" + cluster_ctx
        
        return {
            "vector_results": vector_results,
            "graph_results": graph_results,
            "subgraph": subgraph_data,
            "entities": list(unique_entities.values()),
            "enhanced_context": enhanced_results,
            "query": query,
            "attraction_ids": attraction_ids,
            "primary_attraction_id": primary_attraction_id,
            "errors": errors,
            "intent": intent.value,  # 返回意图类型，便于调试
            "strategy": {k: v for k, v in strategy.items() if k not in ["expand_scenic_attractions"]},  # 返回策略（排除内部标志）
        }

    async def _build_scenic_attractions_context(
        self,
        query: str,
        rag_results: Dict[str, Any],
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """列举景点类问题时，补充“某景区下有哪些景点”的结构化信息。"""
        if not self._is_listing_query(query):
            return ""

        scenic_names: set[str] = set()
        subgraph = rag_results.get("subgraph") or {}
        for node in subgraph.get("nodes", []):
            labels = set(node.get("labels") or [])
            props = node.get("properties") or {}
            if "ScenicSpot" in labels and isinstance(props.get("name"), str):
                scenic_names.add(props["name"])
        if not scenic_names and conversation_history:
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
                    try:
                        check_q = """
                        MATCH (s:ScenicSpot {name: $name})
                        RETURN s.name AS name
                        LIMIT 1
                        """
                        loop = asyncio.get_event_loop()
                        res = await loop.run_in_executor(
                            None,
                            neo4j_client.execute_query,
                            check_q,
                            {"name": cand}
                        )
                        if res and isinstance(res, list) and res[0].get("name"):
                            scenic_names.add(res[0]["name"])
                    except Exception:
                        continue
        if not scenic_names:
            try:
                async def fetch_scenic_names():
                    all_scenic_q = """
                    MATCH (s:ScenicSpot) RETURN s.name AS name LIMIT 5
                    """
                    loop = asyncio.get_event_loop()
                    rows = await loop.run_in_executor(
                        None,
                        neo4j_client.execute_query,
                        all_scenic_q,
                        {}
                    ) or []
                    names = set()
                    for row in rows:
                        nm = row.get("name")
                        if nm and isinstance(nm, str):
                            names.add(nm)
                    return names
                scenic_names = await fetch_scenic_names()
            except Exception as e:
                logger.warning(f"query all ScenicSpot names failed: {e}")

        if not scenic_names:
            return ""
        parts: List[str] = []
        # 并行查询多个景区的景点列表
        tasks = [self._get_scenic_attractions_sentence_by_name(name) for name in list(scenic_names)[:3]]
        sentences = await asyncio.gather(*tasks, return_exceptions=True)
        for sentence in sentences:
            if sentence and not isinstance(sentence, Exception) and sentence.strip():
                parts.append(sentence)

        return "\n".join(parts)
    
    def _get_node_name(self, node: Any) -> str:
        """Neo4j 节点安全取 name。"""
        if node is None:
            return ""
        if isinstance(node, dict):
            return (node.get("name") or (node.get("properties") or {}).get("name") or "").strip()
        if hasattr(node, "get"):
            return (node.get("name") or "").strip()
        return ""

    async def _get_attraction_cluster_context(self, attraction_ids: List[int], max_items: int = 20) -> str:
        """从 Neo4j 拉取景点一簇（属性+出边），格式化为文本供 LLM。"""
        if not attraction_ids:
            return ""
        
        async def fetch_attraction_cluster(aid: int):
            try:
                query = """
                MATCH (a:Attraction {id: $id})
                OPTIONAL MATCH (a)-[r]->(n)
                RETURN a, type(r) as rel_type, n
                """
                loop = asyncio.get_event_loop()
                rows = await loop.run_in_executor(
                    None,
                    neo4j_client.execute_query,
                    query,
                    {"id": int(aid)}
                )
                if not rows:
                    return None
                att_name = ""
                att_desc = ""
                att_location = ""
                att_category = ""
                relations = []
                for row in rows:
                    a = row.get("a")
                    rel_type = row.get("rel_type")
                    n = row.get("n")
                    if a is not None and not att_name:
                        att_name = self._get_node_name(a) or (str(a.get("id")) if hasattr(a, "get") else "")
                        if hasattr(a, "get"):
                            att_desc = (a.get("description") or "").strip()
                            att_location = (a.get("location") or "").strip()
                            att_category = (a.get("category") or "").strip()
                        elif isinstance(a, dict):
                            att_desc = (a.get("description") or (a.get("properties") or {}).get("description") or "").strip()
                            att_location = (a.get("location") or (a.get("properties") or {}).get("location") or "").strip()
                            att_category = (a.get("category") or (a.get("properties") or {}).get("category") or "").strip()
                    if rel_type and n is not None:
                        n_name = self._get_node_name(n)
                        if n_name:
                            relations.append(f"{rel_type} -> {n_name}")
                if not att_name and not relations:
                    return None
                cluster_lines = [f"景点【{att_name or ('ID:' + str(aid))}】"]
                if att_desc:
                    cluster_lines.append(f"描述：{att_desc}")
                if att_location:
                    cluster_lines.append(f"位置：{att_location}")
                if att_category:
                    cluster_lines.append(f"类别：{att_category}")
                if relations:
                    cluster_lines.append("关系与属性：" + "；".join(relations))
                return "\n".join(cluster_lines)
            except Exception as e:
                logger.warning(f"拉取景点簇失败 attraction_id={aid}: {e}")
                return None
        
        unique_ids: List[int] = []
        seen_ids: set[int] = set()
        for aid in attraction_ids:
            try:
                ia = int(aid)
            except Exception:
                continue
            if ia in seen_ids:
                continue
            seen_ids.add(ia)
            unique_ids.append(ia)
            if len(unique_ids) >= max(1, min(int(max_items), 80)):
                break
        results = await asyncio.gather(*[fetch_attraction_cluster(aid) for aid in unique_ids], return_exceptions=True)
        parts = [r for r in results if r and not isinstance(r, Exception)]
        
        if not parts:
            return ""
        return "【景点一簇信息】\n" + "\n\n".join(parts)

    def _parse_scenic_spot_rows(self, rows: List[Dict]) -> str:
        """解析 ScenicSpot 行为景区一簇文本，供按 id/name 共用。"""
        if not rows:
            return ""
        s_name = ""
        s_area = ""
        s_location = ""
        spot_names = []
        feature_names = []
        honor_names = []
        location_name = ""
        for row in rows or []:
            s = row.get("s")
            rel_type = row.get("rel_type")
            n = row.get("n")
            if s is not None and not s_name:
                if hasattr(s, "get"):
                    s_name = (s.get("name") or "").strip()
                    s_area = (s.get("area") or "").strip()
                    s_location = (s.get("location") or "").strip()
                elif isinstance(s, dict):
                    s_name = (s.get("name") or (s.get("properties") or {}).get("name") or "").strip()
                    s_area = (s.get("area") or (s.get("properties") or {}).get("area") or "").strip()
                    s_location = (s.get("location") or (s.get("properties") or {}).get("location") or "").strip()
            if rel_type and n is not None:
                n_name = self._get_node_name(n)
                if not n_name:
                    continue
                if rel_type == "HAS_SPOT":
                    spot_names.append(n_name)
                elif rel_type == "HAS_FEATURE":
                    feature_names.append(n_name)
                elif rel_type == "HAS_HONOR":
                    honor_names.append(n_name)
                elif rel_type == "位于":
                    location_name = n_name
        if not s_name:
            return ""
        lines = [f"景区【{s_name}】"]
        if s_area:
            lines.append(f"面积：{s_area}")
        if s_location:
            lines.append(f"位置：{s_location}")
        if location_name:
            lines.append(f"所在：{location_name}")
        if spot_names:
            lines.append("下属景点：" + "、".join(spot_names[:20]))
        if feature_names:
            lines.append("特色：" + "、".join(feature_names[:15]))
        if honor_names:
            lines.append("荣誉：" + "、".join(honor_names[:10]))
        return "【景区一簇信息】\n" + "\n".join(lines)

    async def _get_scenic_spot_cluster_context(self, scenic_spot_id: int) -> str:
        """按 scenic_spot_id 拉取景区一簇（异步）。"""
        try:
            query = """
            MATCH (s:ScenicSpot {scenic_spot_id: $sid})
            OPTIONAL MATCH (s)-[r]->(n)
            RETURN s, type(r) as rel_type, n
            """
            loop = asyncio.get_event_loop()
            rows = await loop.run_in_executor(
                None,
                neo4j_client.execute_query,
                query,
                {"sid": int(scenic_spot_id)}
            )
            return self._parse_scenic_spot_rows(rows or [])
        except Exception as e:
            logger.warning(f"拉取景区簇失败 scenic_spot_id={scenic_spot_id}: {e}")
            return ""

    async def _get_scenic_spot_cluster_context_by_name(self, scenic_name: str) -> str:
        """按景区名称拉取景区一簇（兼容无 scenic_spot_id 的旧节点，异步）。"""
        if not (scenic_name or "").strip():
            return ""
        try:
            query = """
            MATCH (s:ScenicSpot {name: $name})
            OPTIONAL MATCH (s)-[r]->(n)
            RETURN s, type(r) as rel_type, n
            """
            loop = asyncio.get_event_loop()
            rows = await loop.run_in_executor(
                None,
                neo4j_client.execute_query,
                query,
                {"name": (scenic_name or "").strip()}
            )
            return self._parse_scenic_spot_rows(rows or [])
        except Exception as e:
            logger.warning(f"拉取景区簇失败（按名称） scenic_name={scenic_name}: {e}")
            return ""

    def _get_text_contents_from_neo4j(self, text_ids: List[str]) -> Dict[str, str]:
        """按 text_id 从 Neo4j Text 节点拉取正文（同步方法，由调用方用 run_in_executor 包装）。"""
        if not text_ids:
            return {}
        result = {}
        try:
            query = """
            MATCH (t:Text) WHERE t.id IN $ids
            RETURN t.id AS id, t.content AS content
            """
            rows = neo4j_client.execute_query(query, {"ids": list(text_ids)})
            for row in rows or []:
                tid = row.get("id")
                content = row.get("content")
                if tid is not None and content:
                    result[str(tid)] = (content if isinstance(content, str) else "").strip()
        except Exception as e:
            logger.warning(f"从 Neo4j 拉取文本正文失败: {e}")
        return result

    def _merge_results(self, vector_results: List[Dict], graph_results: List[Dict], entities: List[str]) -> str:
        """融合向量+图检索结果为增强上下文。"""
        context_parts = []
        if vector_results:
            context_parts.append("相关文本内容：")
            for i, result in enumerate(vector_results[:5], 1):
                text_id = result.get("text_id", "")
                score = result.get("score", 0)
                content = result.get("content", "").strip()
                if content:
                    context_parts.append(f"{i}. (相似度: {score:.2f})\n{content}")
                else:
                    context_parts.append(f"{i}. {text_id} (相似度: {score:.2f})")
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
    ) -> Dict[str, Any]:
        """生成回答；RAG 仅在内部执行一次。返回 {answer, primary_attraction_id, context}。"""
        if not self.llm_client:
            return {"answer": "抱歉，AI服务未配置，无法生成回答。", "primary_attraction_id": None, "context": ""}

        out_context = context or ""
        primary_attraction_id: Optional[int] = None
        rag_debug: Optional[Dict[str, Any]] = None
        needs_context = self._query_needs_context(query) if use_rag else False
        if use_rag and not needs_context:
            out_context = "当前问题无需知识库上下文，请自然、简短回复。"
            rag_debug = {
                "query": query,
                "vector_results": [],
                "graph_results": [],
                "subgraph": None,
                "enhanced_context": out_context,
                "entities": [],
                "skip_rag_reason": "问题为寒暄/通用问答，无需检索",
            }
        elif use_rag:
            rag_results = await self.hybrid_search(query, top_k=5)
            primary_attraction_id = rag_results.get("primary_attraction_id")
            out_context = rag_results.get("enhanced_context", "") or ""
            # 如果 hybrid_search 已经扩展了景区信息（通过策略），这里不再重复查询
            # 只在 hybrid_search 未扩展但确实是 listing 意图时，才补充
            detected_intent = rag_results.get("intent")
            already_has_list = "根据图数据库，景区「" in (out_context or "")
            if detected_intent == "listing" and not already_has_list:
                scenic_ctx = await self._build_scenic_attractions_context(
                    query=query,
                    rag_results=rag_results,
                    conversation_history=conversation_history,
                )
                if scenic_ctx:
                    out_context = f"{out_context}\n\n{scenic_ctx}" if out_context else scenic_ctx
                elif rag_results.get("primary_attraction_id") is not None:
                    try:
                        aid = rag_results.get("primary_attraction_id")
                        parent_info = await self._get_scenic_spot_by_attraction_id(aid)
                        scenic_name = parent_info.get("s_name") if parent_info else None
                        if scenic_name:
                            scenic_ctx = await self._get_scenic_attractions_sentence_by_name(str(scenic_name).strip())
                            if scenic_ctx:
                                out_context = f"{out_context}\n\n{scenic_ctx}" if out_context else scenic_ctx
                    except Exception as e:
                        logger.warning(f"列举查询时从primary_attraction_id反查景区失败: {e}")

            rag_debug = {
                "query": rag_results.get("query") or query,
                "vector_results": rag_results.get("vector_results", [])[:5],
                "graph_results": rag_results.get("graph_results", [])[:5],
                "subgraph": rag_results.get("subgraph"),
                "enhanced_context": out_context or "",
                "entities": rag_results.get("entities", []),
                "errors": rag_results.get("errors", {}),
                "intent": rag_results.get("intent"),  # 包含意图信息
                "strategy": rag_results.get("strategy"),  # 包含策略信息
            }
        base_system_prompt = """你是一个专业的景区AI导游助手。请根据提供的上下文信息，用友好、专业、准确的语言回答游客的问题。
回答要求：
1. 基于提供的上下文信息回答
2. 语言简洁明了，适合口语化表达
3. 如果信息不足，诚实说明
4. 不要编造信息
5. 不要透露任何内部标识符/编号/ID（例如 kb_***、text_id、session_id 等）；自我介绍时也不要输出任何“编号”
6. 输出内容必须为“干净的纯文本”：不要使用任何表情/emoji/颜文字，也不要使用装饰性符号（例如 ～、~、🫶、✨、❤️ 等）。只使用正常中文标点（，。！？）与必要的数字/单位。"""
        if character_prompt:
            system_prompt = f"{base_system_prompt}\n\n角色设定：{character_prompt}"
        else:
            system_prompt = base_system_prompt
        messages = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            messages.extend(conversation_history)
        # 根据意图添加针对性提示语
        intent_hint = ""
        if use_rag and rag_debug:
            detected_intent = rag_debug.get("intent") or self._classify_query_intent(query).value
            if detected_intent == "route":
                intent_hint = "说明：用户询问的是游玩/推荐路线，请结合下列多个景点，推荐一条合理的游览顺序（路线），并简要说明每段怎么走或游玩建议。\n\n"
            elif detected_intent == "listing":
                intent_hint = "说明：用户询问的是景点列表或数量，请清晰列出相关景点，并说明总数。\n\n"
            elif detected_intent == "comparison":
                intent_hint = "说明：用户询问的是比较类问题，请对比不同景点的特点、优劣，给出客观建议。\n\n"
            elif detected_intent == "location":
                intent_hint = "说明：用户询问的是位置/导航信息，请重点说明具体位置、地址、如何到达。\n\n"
            elif detected_intent == "feature":
                intent_hint = "说明：用户询问的是特色/功能，请重点说明景点的亮点、好玩之处、推荐理由。\n\n"
            elif detected_intent == "detail":
                intent_hint = "说明：用户询问的是详情/介绍，请提供全面、详细的景点信息。\n\n"
        
        user_prompt = f"""用户问题：{query}
{intent_hint}上下文信息：
{out_context if out_context else "无额外上下文信息"}

请基于以上信息回答用户的问题。"""
        messages.append({"role": "user", "content": user_prompt})
        if rag_debug is not None:
            rag_debug["final_sent_to_llm"] = user_prompt

        try:
            response = self.llm_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=1000
            )
            
            answer = response.choices[0].message.content
            if answer:
                answer = re.sub(r"编号为\s*kb_\d+", "", answer)
                answer = re.sub(r"\bkb_\d+\b", "", answer)
                answer = re.sub(r"\s{2,}", " ", answer).strip()
            if answer:
                answer = _strip_emoji(answer)
                answer = _clean_special_symbols(answer)
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
            return {"answer": answer, "primary_attraction_id": primary_attraction_id, "context": out_context}
        except Exception as e:
            logger.error(f"Failed to generate answer: {e}")
            return {"answer": f"抱歉，生成回答时出现错误：{str(e)}", "primary_attraction_id": None, "context": out_context}


rag_service = RAGService()

