"""GraphRAG 检索服务：图数据库 + 向量检索增强生成"""
import logging
import re
import json
import asyncio
import os
import time
import threading
from collections import OrderedDict
from datetime import datetime, timezone
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

# 线性融合评分默认权重 S(c)=αsvec+βsgraph+γsent 与上下文字符预算
DEFAULT_FUSION_ALPHA = 0.60
DEFAULT_FUSION_BETA = 0.25
DEFAULT_FUSION_GAMMA = 0.15
DEFAULT_CONTEXT_BUDGET_CHARS = 2500

RAG_BASE_SYSTEM_PROMPT = """你是景区智能导游助手，负责为游客提供准确、热情的导览服务。
回答要求：
1. 依据【知识库上下文】与【本会话对话历史中已经确认过的事实】作答；两者之外的信息一律不得编造
2. 当用户追问上一轮提到过的内容（如"旺季多久""那再详细点"），应直接复用对话历史中的事实回答，不得以"无资料"推脱
3. 禁止编造任何数字，票价、距离、时间、面积等数据必须与上下文或对话历史中已给出的数值完全一致
4. 语言口语化、自然热情
5. 当知识库上下文与对话历史均无相关信息时，才回答"这个问题我暂时没有准确资料，建议咨询景区服务中心"
6. 禁止透露任何内部标识符（text_id、session_id、kb_***等）
7. 输出纯文本，禁止使用emoji、Markdown符号（**、#、-列表等）、装饰性符号（～、……、•等）
8. 只使用正常中文标点（，。！？：；），如需列举使用"第一、第二"或"1. 2."格式"""


class QueryIntent(Enum):
    ROUTE = "route"
    LISTING = "listing"
    DETAIL = "detail"
    COMPARISON = "comparison"
    LOCATION = "location"
    FEATURE = "feature"
    GENERAL = "general"


INTENT_CLASSIFY_SYSTEM = """你是景区导览问答系统的意图分类器。根据用户问题（及可选的知识库检索片段）判断用户意图，只输出一个英文单词，不要解释。

意图定义：
- route：路线/行程/怎么走/游玩顺序/推荐路线/一日游路线等
- listing：有哪些/有多少个/列举/列出景点或数量
- detail：介绍/详情/门票/票价/开放时间/描述/说说/讲讲
- comparison：哪个更好/对比/比较/区别/差异
- location：在哪/位置/地址/怎么去/导航/距离/附近
- feature：特色/特点/好玩/玩什么/亮点/推荐理由
- general：寒暄、问候、无法归入以上类型的通用问题

只输出一个词：route、listing、detail、comparison、location、feature、general 之一。"""


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

def _extract_json_str(raw: str) -> str:
    """从 LLM 返回内容中提取 JSON 字符串，处理 markdown 代码块和多余说明。"""
    if not raw:
        return ""
    s = raw.strip()
    # 去掉 ```json ... ``` 或 ``` ... ```
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    s = s.strip()
    # 如果还有多余文字，尝试找第一个 { 到最后一个 }
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        s = s[start:end + 1]
    return s


def _clean_special_symbols(text: str) -> str:
    """清理特殊符号和 Markdown 格式，确保输出为纯文本"""
    if not text or not isinstance(text, str):
        return text or ""
    s = text
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    s = re.sub(r"#+\s*", "", s)
    s = re.sub(r"^[\s]*[-•▪▫]\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"^[\s]*[1-9]\d*[\.、]\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"[～~——…•▪▫]+", "", s)
    s = re.sub(r"[\u0030-\u0039]\uFE0F\u20E3", "", s)
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
        self._embedding_cache: OrderedDict = OrderedDict()
        self._vector_search_cache: OrderedDict = OrderedDict()
        self._cache_stats: Dict[str, int] = {
            "embedding_calls": 0,
            "embedding_hits": 0,
            "embedding_misses": 0,
            "vector_calls": 0,
            "vector_hits": 0,
            "vector_misses": 0,
        }
        self._model_ready = threading.Event()  # RAG 请求到来时等待模型加载完毕
        self._init_ner()
        self._init_llm_client()
        threading.Thread(target=self._init_embedding_model, daemon=True).start()

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
        self._embedding_cache.move_to_end(key)
        return payload

    def _cache_set_embedding(self, key: str, payload: List[float]) -> None:
        ttl = max(0, int(EMBEDDING_CACHE_TTL_SECONDS))
        expires_at = _monotonic() + ttl if ttl > 0 else 0.0
        if key in self._embedding_cache:
            self._embedding_cache.move_to_end(key)
        elif len(self._embedding_cache) >= EMBEDDING_CACHE_MAX_SIZE:
            self._embedding_cache.popitem(last=False)
        self._embedding_cache[key] = (payload, expires_at)

    def _cache_get_vector(self, key) -> Optional[List[Dict[str, Any]]]:
        item = self._vector_search_cache.get(key)
        if not item:
            return None
        payload, expires_at = item
        if expires_at > 0 and _monotonic() >= expires_at:
            self._vector_search_cache.pop(key, None)
            return None
        self._vector_search_cache.move_to_end(key)
        return payload

    def _cache_set_vector(self, key, payload: List[Dict[str, Any]]) -> None:
        ttl = max(0, int(VECTOR_SEARCH_CACHE_TTL_SECONDS))
        expires_at = _monotonic() + ttl if ttl > 0 else 0.0
        if key in self._vector_search_cache:
            self._vector_search_cache.move_to_end(key)
        elif len(self._vector_search_cache) >= VECTOR_SEARCH_CACHE_MAX_SIZE:
            self._vector_search_cache.popitem(last=False)
        self._vector_search_cache[key] = (payload, expires_at)

    async def parse_scenic_text(self, text: str) -> Optional[Dict[str, Any]]:
        """将景区介绍结构化为 JSON 供图库建簇；非景区类返回 None。"""
        scenic_keywords = ["景区", "风景区", "旅游度假区", "景点", "度假区"]
        if not any(k in text for k in scenic_keywords):
            return None

        if not self.llm_client:
            return None

        system_prompt = """
你是景区知识结构化助手。请把一段中文景区介绍或景区说明（包括票务政策、开放时间、交通、服务设施等）提取成 JSON，严格按字段返回，不要多余说明。

统一命名规范（非常重要，用于控制图谱中的节点与关系）：
1）scenic_spot：输出景区的正式全称，例如"蜀南竹海景区"或"蜀南竹海旅游度假区"，不要只输出"蜀南竹海"三个字。
2）spots 数组中的每个元素是"子景点/核心游览点"的常用短名称，例如"海中海""观光索道""竹尖漫步"，不要带"景点""景区"等后缀。
3）features / awards 中的每个元素是简洁的名词短语，例如"森林覆盖率高""世界竹子公园""国家级旅游度假区"，不要写成很长的句子。
4）所有数组中的名称，尽量避免重复、避免包含明显无意义的词（比如"这里""景区里"等）。

返回字段：
- scenic_spot: 景区名称（字符串，按上述规范）
- location: 行政层级数组，例如 ["四川省", "宜宾市", "长宁县"]（若缺少下级可省略）
- area: 面积（原文中的描述字符串，若没有则为 null）
- features: 特色数组，例如 ["天然竹林","森林覆盖率93%","气候温和","雨量充沛"]
- spots: 子景点数组，例如 ["竹海博物馆","花溪十三桥","海中海","古刹"]
- awards: 荣誉数组，例如 ["国家首批4A级旅游区","全国康养旅游基地","国家级旅游度假区"]
- ticket_info: 门票与优惠政策的综合说明（字符串，若没有则为 null），请用一两段话概括门票价格、优惠人群及年卡等信息
- opening_hours: 开放时间与各类项目营业时间的综合说明（字符串，若没有则为 null）
- transport_info: 景区内外交通信息的综合说明（字符串，包含自驾、公交/景区巴士、索道等，若没有则为 null）
- service_facilities: 服务设施说明（字符串，如停车场、卫生间、游客中心、便利店等，若没有则为 null）

若某字段在原文中完全没有提到，请返回 null（不要返回空字符串），数组字段若没有则返回空数组 []。
只输出 JSON 对象，不要解释。
"""
        try:
            resp = await asyncio.to_thread(
                self.llm_client.chat.completions.create,
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                temperature=0.1,
                max_tokens=512,
            )
            raw = resp.choices[0].message.content
            data = json.loads(_extract_json_str(raw))
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
你是景点知识结构化助手。请把一段中文"单个景点"的介绍提取成 JSON，严格按字段返回，不要多余说明。

统一命名规范（用于控制图谱中的节点与关系）：
1）name：输出该景点在图谱中要使用的标准名称，尽量为常用短名，例如"海中海""竹海博物馆"，不要包含"景点""景区"等后缀。
2）category：尽量使用简洁类别词，例如"自然风光""人文景观""游乐项目""观光索道"等。
3）features / honors 数组中的每个元素是简洁的名词短语，例如"竹筏漂流体验""国家 4A 级景区核心景点"，不要写成很长的句子。

返回字段：
- name: 景点名称（字符串，按上述规范）
- location: 行政层级数组，例如 ["四川省", "宜宾市", "长宁县"]（若无法判断则返回 []）
- category: 类别（字符串或 null）
- features: 特色/要点数组（若没有则 []）
- honors: 荣誉/称号数组（若没有则 []）

只输出 JSON 对象，不要解释。
"""
        try:
            resp = await asyncio.to_thread(
                self.llm_client.chat.completions.create,
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"景点名称：{name}\n\n{text}"},
                ],
                temperature=0.1,
                max_tokens=512,
            )
            raw = resp.choices[0].message.content
            data = json.loads(_extract_json_str(raw))
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
        import os as _os
        _os.environ.setdefault("HF_HUB_OFFLINE", "1")
        _os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        _proxy_keys = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                       "http_proxy", "https_proxy", "all_proxy")
        _saved = {k: _os.environ.pop(k) for k in _proxy_keys if k in _os.environ}
        try:
            self.embedding_model = SentenceTransformer(RAG_EMBEDDING_MODEL_NAME)
            logger.info("Embedding model loaded: %s", RAG_EMBEDDING_MODEL_NAME)
        except Exception as e:
            logger.error("Failed to load embedding model: %s", e)
            self.embedding_model = None
        finally:
            _os.environ.update(_saved)
            self._model_ready.set()  
    
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
                import openai, httpx
                client_kwargs = {"api_key": settings.OPENAI_API_KEY}
                if settings.OPENAI_API_BASE:
                    client_kwargs["base_url"] = settings.OPENAI_API_BASE
                self.llm_client = openai.OpenAI(
                    http_client=httpx.Client(
                        trust_env=False,
                        timeout=httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=5.0),
                    ),
                    **client_kwargs,
                )
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
        self._model_ready.wait()  # 后台线程尚未加载完时阻塞，通常几秒内完成
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
        self._model_ready.wait()
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
                results.append([])

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

        cache_key = (query.strip(), collection_name, top_k, RAG_EMBEDDING_MODEL_NAME)
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

        start_time = datetime.now(timezone.utc)

        def _blocking_search() -> List[Dict[str, Any]]:
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
                    logger.warning("Collection '%s' does not exist", collection_name)
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
                        collection.load()
                    self._milvus_loaded_collections.add(collection_name)
                except Exception as e:
                    logger.warning(
                        "Failed to ensure collection '%s' loaded, will rely on retry: %s",
                        collection_name,
                        e,
                    )

            query_vector = [self.generate_embedding(query)]
            search_params = {
                "metric_type": str(MILVUS_METRIC_TYPE or "L2"),
                "params": {"nprobe": int(MILVUS_NPROBE or 10)},
            }
            try:
                results = collection.search(
                    data=query_vector,
                    anns_field="embedding",
                    param=search_params,
                    limit=top_k,
                    output_fields=["text_id", "content"],
                )
            except Exception as e:
                if "not loaded" in str(e).lower() or "collection not loaded" in str(e).lower():
                    try:
                        collection.load()
                        self._milvus_loaded_collections.add(collection_name)
                        results = collection.search(
                            data=query_vector,
                            anns_field="embedding",
                            param=search_params,
                            limit=top_k,
                            output_fields=["text_id", "content"],
                        )
                    except Exception as retry_error:
                        logger.error("Retry search failed: %s", retry_error)
                        return []
                else:
                    logger.error("Search failed: %s", e)
                    return []

            out: List[Dict[str, Any]] = []
            if results and len(results) > 0:
                for hit in results[0]:
                    out.append(
                        {
                            "id": hit.id,
                            "text_id": hit.entity.get("text_id", ""),
                            "content": hit.entity.get("content", ""),
                            "distance": hit.distance,
                            "score": 1 / (1 + hit.distance) if hit.distance > 0 else 1.0,
                        }
                    )
            return out

        loop = asyncio.get_event_loop()
        search_results = await loop.run_in_executor(None, _blocking_search)
        
        elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
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
              WITH a, r, b, labels(a) as a_labels, labels(b) as b_labels, type(r) as rel_type,
                   CASE WHEN a.name = name THEN 0 ELSE 1 END AS priority
              ORDER BY priority
              RETURN a, r, b, a_labels, b_labels, rel_type
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
        """基于多实体构建子图。"""
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
        """判断当前问题是否需要走 RAG。"""
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
        """判断是否为"景点列表/数量"类问题。"""
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

    def _has_pronoun_reference(self, query: str) -> bool:
        """判断查询是否包含指代词（这个景区、这个景点、这里等），需要从对话历史解析。"""
        if not query or not isinstance(query, str):
            return False
        q = query.strip()
        patterns = [
            r"这个景区|这个景点|那个景区|那个景点",
            r"这里(怎么样|有什么|有哪些|介绍|好玩)",
            r"那里(怎么样|有什么|有哪些|介绍|好玩)",
            r"介绍一下这个|介绍一下那个",
            r"这个(地方|景区|景点).*(介绍|怎么样|有什么)",
            r"那个(地方|景区|景点).*(介绍|怎么样|有什么)",
            r"第[一二三四五六七八九十百\d]+个",
            r"(上面|刚才|前面).*(第|说的|提到的)",
        ]
        return any(re.search(p, q) for p in patterns)

    async def _resolve_ordinal_from_neo4j(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]],
        scenic_name: Optional[str] = None,
    ) -> Optional[str]:
        """从 Neo4j 景点有序列表解析序号指代，如"第7个"→"永江休闲度假村"。"""
        cn_num_map = {
            "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
            "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
        }
        ordinal_match = re.search(r"第([一二三四五六七八九十]+|\d+)\s*个", query)
        if not ordinal_match:
            return None
        raw = ordinal_match.group(1)
        index = int(raw) if raw.isdigit() else cn_num_map.get(raw)
        if not index:
            return None
        # 确定景区名称
        name = (scenic_name or "").strip()
        if not name and conversation_history:
            entities = self._extract_entities_from_history(conversation_history)
            name = entities[0] if entities else ""
        if not name:
            return None
        try:
            _, names = await self._get_scenic_attraction_ids_and_names(name)
            if names and index <= len(names):
                return names[index - 1]
        except Exception as e:
            logger.debug(f"_resolve_ordinal_from_neo4j 失败: {e}")
        return None

    @staticmethod
    def _resolve_ordinal_reference(
        query: str, conversation_history: Optional[List[Dict[str, str]]]
    ) -> Optional[str]:
        """将查询中的序号指代（如"第五个"）解析为对话历史中对应的景点名称。"""
        if not query or not conversation_history:
            return None
        # 提取查询中的序号
        cn_num_map = {
            "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
            "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
        }
        ordinal_match = re.search(r"第([一二三四五六七八九十]+|\d+)\s*个", query)
        if not ordinal_match:
            return None
        raw = ordinal_match.group(1)
        index = int(raw) if raw.isdigit() else cn_num_map.get(raw)
        if not index:
            return None
        for msg in reversed(conversation_history[-10:]):
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content", "")
            matches = re.findall(r"第[一二三四五六七八九十]+[\s，,、]?([^\s，,、（(第\d]{2,15})(?=[，,、（(\d第]|$)", content)
            if matches and index <= len(matches):
                return matches[index - 1]
            matches2 = re.findall(r"\d+[\.、．]\s*([^\s（(，,、\n]{2,15})(?=[（(，,、\n\d]|$)", content)
            if matches2 and index <= len(matches2):
                return matches2[index - 1]
            dun_blocks = re.findall(r"[\u4e00-\u9fa5a-zA-Z0-9]{2,12}(?:、[\u4e00-\u9fa5a-zA-Z0-9]{2,12}){4,}", content)
            for block in dun_blocks:
                items = block.split("、")
                if index <= len(items):
                    return items[index - 1]
        return None

    def _extract_entities_from_history(
        self, conversation_history: Optional[List[Dict[str, str]]]
    ) -> List[str]:
        """从对话历史中提取景区/景点名称，用于指代消解。"""
        if not conversation_history or not isinstance(conversation_history, list):
            return []
        recent_texts: List[str] = []
        for msg in conversation_history[-8:]:
            role = msg.get("role")
            content = msg.get("content")
            if content and isinstance(content, str) and role in ("user", "assistant"):
                recent_texts.append(content)
        if not recent_texts:
            return []
        combined = " ".join(recent_texts)
        entities = self.extract_entities(combined)
        generic = {"介绍", "详情", "位置", "路线", "怎么", "好玩", "推荐", "谢谢", "好的", "可以"}
        names = []
        for e in entities:
            t = (e.get("text") or "").strip()
            if not t or len(t) < 2 or len(t) > 15 or t in generic:
                continue
            names.append(t)
        return names[:5]

    @staticmethod
    def _fast_classify_intent(query: str) -> Optional["QueryIntent"]:
        """关键词快速意图分类，命中则直接返回，无需 LLM 调用（0ms）。"""
        q = query.strip()
        if not q:
            return QueryIntent.GENERAL
        route_kw = ("路线", "行程", "规划", "怎么玩", "怎么游", "游览顺序", "先去哪", "先看哪",
                    "游玩路线", "一日游", "半日游", "游览路线", "参观顺序", "怎么安排", "如何安排",
                    "游览计划", "旅游路线", "建议路线")
        if any(k in q for k in route_kw):
            return QueryIntent.ROUTE
        listing_kw = ("有哪些", "有什么景点", "景点有哪", "哪些景点", "列一下", "列举",
                      "所有景点", "全部景点", "包含哪些", "有几个", "景点列表", "都有什么",
                      "有什么地方", "有哪些地方", "包括哪些", "有什么好玩",
                      "多少个景点", "几个景点", "有多少景点", "共有多少", "一共多少",
                      "有多少个", "总共有多少", "景点数量")
        if any(k in q for k in listing_kw):
            return QueryIntent.LISTING
        detail_kw = ("介绍", "详情", "说说", "讲讲", "是什么", "是啥", "开放时间", "营业时间",
                     "门票", "票价", "怎么去", "交通", "简介", "历史", "来历", "背景",
                     "特点", "有名", "著名", "出名", "闻名", "故事", "传说", "文化")
        if any(k in q for k in detail_kw):
            return QueryIntent.DETAIL
        comparison_kw = ("和", "与", "比较", "对比", "区别", "哪个好", "哪个更", "还是",
                         "相比", "比起", "差异", "不同")
        if sum(1 for k in comparison_kw if k in q) >= 2:
            return QueryIntent.COMPARISON
        location_kw = ("在哪", "在哪里", "怎么走", "位置", "地址", "地点", "地图",
                       "怎么到", "如何到", "路怎么走", "导航", "距离")
        if any(k in q for k in location_kw):
            return QueryIntent.LOCATION
        feature_kw = ("特色", "特产", "美食", "好吃", "推荐", "值得", "适合", "适宜",
                      "最好", "最美", "最值", "打卡", "网红", "拍照", "风景", "景色",
                      "季节", "最佳时间", "几月", "什么时候去")
        if any(k in q for k in feature_kw):
            return QueryIntent.FEATURE
        # 短句直接问景点名 → DETAIL
        if len(q) <= 12 and not any(c in q for c in ("？", "?", "吗", "呢", "啊")):
            return QueryIntent.DETAIL
        return None  # 不确定，交给 LLM

    async def _classify_query_intent(self, query: str) -> QueryIntent:
        """基于 LLM + RAG 的意图分类：先做轻量向量检索提供上下文，再由 LLM 判断意图。"""
        if not query or not isinstance(query, str):
            return QueryIntent.GENERAL
        q = query.strip()
        if not q:
            return QueryIntent.GENERAL

        fast_result = self._fast_classify_intent(q)
        if fast_result is not None:
            logger.debug("意图分类（关键词）: %s -> %s", q[:50], fast_result.value)
            return fast_result

        if not self.llm_client:
            logger.debug("LLM 未配置，意图默认为 general")
            return QueryIntent.GENERAL

        try:
            _msgs = [
                {"role": "system", "content": INTENT_CLASSIFY_SYSTEM},
                {"role": "user", "content": f"用户问题：{q}"},
            ]
            response = await asyncio.to_thread(
                self.llm_client.chat.completions.create,
                model=settings.OPENAI_MODEL,
                messages=_msgs,
                temperature=0,
                max_tokens=20,
                timeout=3,
            )
            text = (response.choices[0].message.content or "").strip().lower()
            for word in text.split():
                word = word.rstrip(".,;:?!")
                for intent in QueryIntent:
                    if intent.value == word:
                        logger.debug("意图分类 LLM 结果: %s -> %s", q[:50], intent.value)
                        return intent
            logger.debug("意图分类 LLM 未识别到有效意图，原文: %s，默认 general", text[:80])
        except Exception as e:
            logger.warning("意图分类 LLM 调用失败，回退为 general: %s", e)
        return QueryIntent.GENERAL

    def _get_search_strategy(self, intent: QueryIntent) -> Dict[str, Any]:
        """根据意图返回检索策略配置。"""
        strategies = {
            QueryIntent.ROUTE: {
                "top_k": 10,
                "relevance_threshold": 0.1,
                "graph_depth": 3,
                "expand_scenic_attractions": True,
                "max_attractions": 15,
                "force_at_least_one": True,
            },
            QueryIntent.LISTING: {
                "top_k": 8,
                "relevance_threshold": 0.15,
                "graph_depth": 2,
                "expand_scenic_attractions": True,
                "max_attractions": 30,
                "force_at_least_one": True,
            },
            QueryIntent.DETAIL: {
                "top_k": 3,
                "relevance_threshold": 0.1,
                "graph_depth": 1,
                "expand_scenic_attractions": False,
                "max_attractions": 1,
                "force_at_least_one": True,
            },
            QueryIntent.COMPARISON: {
                "top_k": 8,
                "relevance_threshold": 0.2,
                "graph_depth": 2,
                "expand_scenic_attractions": False,
                "max_attractions": 5,
                "force_at_least_one": True,
            },
            QueryIntent.LOCATION: {
                "top_k": 5,
                "relevance_threshold": 0.2,
                "graph_depth": 2,
                "expand_scenic_attractions": False,
                "max_attractions": 1,
                "force_at_least_one": True,
            },
            QueryIntent.FEATURE: {
                "top_k": 6,
                "relevance_threshold": 0.2,
                "graph_depth": 2,
                "expand_scenic_attractions": False,
                "max_attractions": 3,
                "force_at_least_one": True,
            },
            QueryIntent.GENERAL: {
                "top_k": 5,
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

    def _extract_attraction_candidates_from_query(self, query: str) -> List[str]:
        """从「介绍/详情/说说 + 景点名」类问句中显式抽取景点名，避免 jieba 未切出时漏检。"""
        if not query or not isinstance(query, str):
            return []
        q = query.strip()
        if len(q) < 2:
            return []
        candidates: List[str] = []
        patterns = [
            r"(?:介绍|详情|说说|讲讲|了解)(?:一下|一|下)?\s*([\u4e00-\u9fa5]{2,10})",
            r"([\u4e00-\u9fa5]{2,10})\s*(?:怎么样|如何|在哪|有什么|好玩吗)",
        ]
        stop = {"介绍", "详情", "说说", "讲讲", "了解", "怎么样", "如何", "有什么", "好玩", "地方", "景区", "景点"}
        for pat in patterns:
            for m in re.finditer(pat, q):
                name = (m.group(1) or "").strip()
                if name and name not in stop and name not in candidates:
                    candidates.append(name)
        return candidates[:5]

    async def _get_attraction_id_by_name(self, attraction_name: str) -> Optional[int]:
        """按景点名称在图里查 Attraction，返回 id；先精确匹配，再 CONTAINS 模糊匹配。"""
        result = await self._get_first_attraction_id_by_names([attraction_name])
        return result

    async def _get_first_attraction_id_by_names(self, names: List[str]) -> Optional[int]:
        """批量查询景点 id，单次 Cypher 完成精确+模糊匹配，返回第一个命中的 id。
        替代原来对多个名字的串行 N+1 调用。"""
        clean = [n.strip() for n in (names or []) if n and n.strip()]
        if not clean:
            return None
        loop = asyncio.get_event_loop()
        try:
            rows = await loop.run_in_executor(
                None,
                neo4j_client.execute_query,
                """
                UNWIND $names AS nm
                OPTIONAL MATCH (exact:Attraction) WHERE exact.name = nm
                OPTIONAL MATCH (fuzzy:Attraction) WHERE fuzzy.name CONTAINS nm
                WITH nm,
                     CASE WHEN exact IS NOT NULL THEN exact.id ELSE null END AS exact_id,
                     CASE WHEN fuzzy IS NOT NULL THEN fuzzy.id ELSE null END  AS fuzzy_id,
                     CASE WHEN exact IS NOT NULL THEN 0 ELSE 1 END            AS priority
                WITH coalesce(exact_id, fuzzy_id) AS aid, priority
                WHERE aid IS NOT NULL
                RETURN aid AS id ORDER BY priority LIMIT 1
                """,
                {"names": clean},
            )
            if rows and rows[0].get("id") is not None:
                return int(rows[0]["id"])
        except Exception as e:
            logger.debug("_get_first_attraction_id_by_names %s: %s", clean, e)

        # 字符重叠兜底：适用于单字打错的情况（如"仙禹洞"→"仙寓洞"）
        try:
            all_rows = await loop.run_in_executor(
                None,
                neo4j_client.execute_query,
                "MATCH (a:Attraction) WHERE a.id IS NOT NULL AND a.name IS NOT NULL RETURN a.id AS id, a.name AS name LIMIT 200",
                {},
            ) or []
            all_attractions = [(int(r["id"]), str(r["name"]).strip()) for r in all_rows if r.get("id") and r.get("name")]
            best_id, best_score = None, 0.0
            for qname in clean:
                if len(qname) < 2:
                    continue
                q_chars = set(qname)
                for aid, aname in all_attractions:
                    common = len(q_chars & set(aname))
                    score = common / len(qname)
                    if common >= 2 and score >= 0.6 and score > best_score:
                        best_score, best_id = score, aid
            if best_id is not None:
                logger.debug("_get_first_attraction_id_by_names char-overlap match: %s -> id=%s (score=%.2f)", clean, best_id, best_score)
                return best_id
        except Exception as e:
            logger.debug("_get_first_attraction_id_by_names char-overlap %s: %s", clean, e)
        return None

    async def _fetch_scenic_spot_names(self, limit: int = 5) -> List[str]:
        """从图库查询景区名称列表（用于兜底列举等），避免多处重复相同 Cypher。"""
        try:
            loop = asyncio.get_event_loop()
            rows = await loop.run_in_executor(
                None,
                neo4j_client.execute_query,
                "MATCH (s:ScenicSpot) RETURN s.name AS name LIMIT $limit",
                {"limit": max(1, min(limit, 20))},
            ) or []
            return [str(r["name"]).strip() for r in rows if r.get("name")]
        except Exception as e:
            logger.debug("_fetch_scenic_spot_names: %s", e)
            return []

    async def _get_scenic_spot_name_if_exists(self, name: str) -> Optional[str]:
        """图库中若存在名为 name 的 ScenicSpot 则返回该名称，否则返回 None。用于实体名是否景区判断。"""
        if not (name or "").strip():
            return None
        try:
            loop = asyncio.get_event_loop()
            rows = await loop.run_in_executor(
                None,
                neo4j_client.execute_query,
                "MATCH (s:ScenicSpot {name: $name}) RETURN s.name AS name LIMIT 1",
                {"name": (name or "").strip()},
            )
            if rows and isinstance(rows, list) and rows[0].get("name"):
                return str(rows[0]["name"]).strip()
        except Exception:
            pass
        return None

    async def _get_scenic_attractions_sentence_by_name(self, scenic_name: str) -> str:
        """根据景区名称查询其下相关景点，并格式化为一句话描述（复用 _get_scenic_attraction_ids_and_names）。"""
        name = (scenic_name or "").strip()
        if not name:
            return ""
        _, names = await self._get_scenic_attraction_ids_and_names(name)
        return self._format_scenic_attractions_sentence(name, names) if names else ""

    def _format_scenic_attractions_sentence(self, scenic_name: str, attraction_names: List[str]) -> str:
        """将景点名称列表格式化为一句描述（与 _get_scenic_attractions_sentence_by_name 共用格式）。"""
        if not attraction_names or not (scenic_name or "").strip():
            return ""
        count = len(attraction_names)
        joined = "、".join(attraction_names[:20])
        return f"根据图数据库，景区「{(scenic_name or '').strip()}」下的相关景点共有 {count} 个，包括：{joined}。"

    async def _get_scenic_attraction_ids_and_names(self, scenic_name: str) -> Tuple[List[int], List[str]]:
        """根据景区名称查询其下景点 ID 与名称，供路线/列举等一次查询复用。"""
        name = (scenic_name or "").strip()
        if not name:
            return [], []
        try:
            q = """
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
                None, neo4j_client.execute_query, q, {"name": name}
            ) or []
            aids: List[int] = []
            names: List[str] = []
            for r in rows:
                if r and r.get("aid") is not None:
                    try:
                        aids.append(int(r["aid"]))
                        nm = r.get("name")
                        if nm and not str(nm).strip().startswith("kb_"):
                            names.append(str(nm))
                    except Exception:
                        continue
            return aids, names
        except Exception as e:
            logger.warning("_get_scenic_attraction_ids_and_names %s: %s", name, e)
            return [], []

    async def hybrid_search(
        self,
        query: str,
        top_k: int = 5,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        scenic_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        意图驱动的混合检索：向量检索 + 实体识别 + 图检索 + 结果融合。
        根据查询意图自动选择最优检索策略（top_k、阈值、图查询深度等）。
        当查询含指代词（如「这个景区」）时，优先用 scenic_name（用户选择的景区），
        否则从 conversation_history 解析实体并补充检索。
        """
        q_stripped = (query or "").strip()
        is_ticket_query = any(
            k in q_stripped for k in ("门票", "票价", "成人票", "学生票", "半票", "优惠票", "年卡", "票多少钱", "票多钱", "票多少")
        )

        resolved_entities: List[str] = []
        scenic_name_str = (scenic_name or "").strip()
        if scenic_name_str:
            resolved_entities = [scenic_name_str]
            logger.debug(f"使用用户选择景区: {scenic_name_str}")
        elif self._has_pronoun_reference(query) and conversation_history:
            # 优先用 Neo4j 解析序号指代（比解析 LLM 文本更可靠）
            ordinal_name = await self._resolve_ordinal_from_neo4j(query, conversation_history, scenic_name)
            if ordinal_name:
                resolved_entities = [ordinal_name]
                logger.debug(f"序号指代消解(Neo4j): 第N个 -> {ordinal_name}")
            else:
                # fallback: 解析对话历史文本
                ordinal_name = self._resolve_ordinal_reference(query, conversation_history)
                if ordinal_name:
                    resolved_entities = [ordinal_name]
                    logger.debug(f"序号指代消解(文本): 第N个 -> {ordinal_name}")
                else:
                    resolved_entities = self._extract_entities_from_history(conversation_history)
            if resolved_entities:
                logger.debug(f"指代消解: 从历史解析实体 {resolved_entities}")

        effective_query = query
        if resolved_entities:
            effective_query = f"{' '.join(resolved_entities[:2])} {query}"

        errors: Dict[str, str] = {}
        try:
            intent, vector_results_raw = await asyncio.gather(
                self._classify_query_intent(query),
                self.vector_search(effective_query, top_k=10),
            )
        except Exception as e:
            intent = QueryIntent.GENERAL
            vector_results_raw = []
            errors["milvus"] = str(e)
            logger.warning("hybrid_search parallel gather failed: %s", e)

        strategy = self._get_search_strategy(intent)
        effective_top_k = top_k if top_k != 5 else strategy["top_k"]
        effective_threshold = strategy["relevance_threshold"]
        graph_depth = strategy["graph_depth"]
        vector_results = (vector_results_raw or [])[:effective_top_k]

        logger.debug(f"查询意图: {intent.value}, top_k={effective_top_k}, threshold={effective_threshold}, graph_depth={graph_depth}")
        if vector_results:
            score_info = [(r.get("text_id"), round(r.get("score", 0), 4)) for r in vector_results]
            logger.info(f"向量检索原始结果({len(vector_results)}条): {score_info}")

        vector_results_relevant = [
            r
            for r in (vector_results or [])
            if (r.get("score") or 0) >= effective_threshold
        ]
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
        seen_set = set(entity_names)
        for name in resolved_entities:
            if name and name not in seen_set:
                entity_names = entity_names + [name]
                seen_set.add(name)
        
        text_ids_to_fetch = [
            (r.get("text_id") or "").strip()
            for r in (vector_results or [])
            if (r.get("text_id") or "").strip() and not (r.get("text_id") or "").strip().startswith("attraction_")
        ]
        
        graph_results: List[Dict[str, Any]] = []
        subgraph_data = None
        if entity_names:
            per_entity_limit = 12 if intent == QueryIntent.LISTING else (8 if intent == QueryIntent.ROUTE else 5)
            tasks = [
                self._graph_search_many(entity_names[:5], per_entity_limit=per_entity_limit),
            ]
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
        enhanced_results, scored_candidates = self._build_scored_context(
            vector_results=vector_results or [],
            graph_results=graph_results or [],
            entity_names=entity_names,
            resolved_entities=resolved_entities,
            scenic_name=scenic_name_str,
        )
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
        
        should_expand = strategy.get("expand_scenic_attractions", False)
        max_attractions = strategy.get("max_attractions", 1)
        
        if should_expand and primary_attraction_id is not None:
            try:
                parent_info = await self._get_scenic_spot_by_attraction_id(primary_attraction_id)
                if parent_info:
                    s_name = str(parent_info.get("s_name") or "").strip()
                    if s_name:
                        enhanced_results, _ = await self._append_scenic_cluster(
                            s_name, enhanced_results or "", intent, max_attractions
                        )
            except Exception as e:
                logger.warning(f"扩展景区景点失败 (intent={intent.value}): {e}")

        if should_expand and intent in (QueryIntent.LISTING, QueryIntent.ROUTE) and "【景点一簇信息】" not in (enhanced_results or ""):
            try:
                candidate_names = list(dict.fromkeys(
                    ([scenic_name_str] if scenic_name_str else []) +
                    [e for e in (entity_names or []) if e]
                ))
                for cname in candidate_names[:5]:
                    updated, found = await self._append_scenic_cluster(
                        cname, enhanced_results or "", intent, max_attractions
                    )
                    if found:
                        enhanced_results = updated
                        break
            except Exception as e:
                logger.warning(f"LISTING/ROUTE 兜底扩展景区景点失败: {e}")

        if intent == QueryIntent.LISTING and "根据图数据库，景区「" not in (enhanced_results or ""):
            try:
                async def fetch_first_scenic_listing():
                    if scenic_name_str:
                        sentence = await self._get_scenic_attractions_sentence_by_name(scenic_name_str)
                        if sentence:
                            return sentence
                    for nm in await self._fetch_scenic_spot_names(5):
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
        if intent == QueryIntent.DETAIL and scenic_name_str and (not primary_attraction_id or is_ticket_query or query_about_scenic):
            try:
                scenic_ctx_detail = await self._get_scenic_spot_cluster_context_by_name(scenic_name_str)
                if scenic_ctx_detail:
                    enhanced_results = (scenic_ctx_detail + "\n\n" + (enhanced_results or "")).strip()
                    if query_about_scenic:
                        scenic_ctx_found = True  # 已注入景区簇，阻止后续景点簇注入
            except Exception as e:
                logger.warning(f"DETAIL 查询补充景区簇上下文失败: {e}")
        if query_about_scenic and not (intent == QueryIntent.DETAIL and scenic_name_str):
            scenic_tasks = []
            if primary_attraction_id is not None:
                async def get_scenic_from_attraction():
                    try:
                        parent_info = await self._get_scenic_spot_by_attraction_id(primary_attraction_id)
                        if not parent_info:
                            return ""
                        sid, s_name = parent_info.get("sid"), parent_info.get("s_name")
                        if sid is not None:
                            return await self._get_scenic_spot_cluster_context_impl(scenic_spot_id=int(sid))
                        if s_name:
                            return await self._get_scenic_spot_cluster_context_impl(scenic_name=str(s_name).strip())
                    except Exception as e:
                        logger.warning("查询景点所属景区失败: %s", e)
                    return ""
                scenic_tasks.append(get_scenic_from_attraction())
            if entity_names:
                for entity_name in entity_names[:3]:
                    scenic_tasks.append(self._get_scenic_spot_cluster_by_entity_name(entity_name))
            if scenic_name_str:
                scenic_tasks.append(self._get_scenic_spot_cluster_context_by_name(scenic_name_str))
            
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
                    
        if (
            not should_expand
            and not (query_about_scenic and scenic_ctx_found)
            and not is_ticket_query
        ):
            intro_candidates = self._extract_attraction_candidates_from_query(query)
            names_to_try = list(dict.fromkeys([n.strip() for n in intro_candidates if n and n.strip()]))
            for n in entity_names[:5]:
                ns = n.strip() if n else ""
                # 跳过景区名（避免 "蜀南竹海" CONTAINS 匹配到 "蜀南竹海博物馆"）
                if ns and ns not in names_to_try and ns != scenic_name_str:
                    names_to_try.append(ns)
            entity_aid = await self._get_first_attraction_id_by_names(names_to_try[:8]) if names_to_try else None
            # 只在明确从查询中识别到景点时才注入簇，避免回退到向量结果首条造成错误注入
            target_aid = entity_aid
            if target_aid is not None:
                cluster_ctx = await self._get_attraction_cluster_context([target_aid], max_items=1)
                if cluster_ctx:
                    enhanced_results = (enhanced_results or "") + "\n\n" + cluster_ctx
        
        return {
            "vector_results": vector_results,
            "graph_results": graph_results,
            "subgraph": subgraph_data,
            "entities": list(unique_entities.values()),
            "enhanced_context": enhanced_results,
            "scored_candidates": scored_candidates[:10],
            "query": query,
            "attraction_ids": attraction_ids,
            "primary_attraction_id": primary_attraction_id,
            "errors": errors,
            "intent": intent.value,
            "strategy": {k: v for k, v in strategy.items() if k not in ["expand_scenic_attractions"]},
        }

    async def _build_scenic_attractions_context(
        self,
        query: str,
        rag_results: Dict[str, Any],
        conversation_history: Optional[List[Dict[str, str]]] = None,
        scenic_name: Optional[str] = None,
    ) -> str:
        """列举景点类问题时，补充"某景区下有哪些景点"的结构化信息。"""
        if not self._is_listing_query(query):
            return ""

        scenic_names: set[str] = set()
        if (scenic_name or "").strip():
            scenic_names.add((scenic_name or "").strip())
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
                    existing = await self._get_scenic_spot_name_if_exists(cand)
                    if existing:
                        scenic_names.add(existing)
        if not scenic_names:
            try:
                names_list = await self._fetch_scenic_spot_names(5)
                scenic_names = set(n for n in names_list if n)
            except Exception as e:
                logger.warning(f"query all ScenicSpot names failed: {e}")

        if not scenic_names:
            return ""
        parts: List[str] = []
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

    async def _append_scenic_cluster(
        self,
        scenic_name: str,
        enhanced_results: str,
        intent: "QueryIntent",
        max_attractions: int,
    ) -> Tuple[str, bool]:
        """为指定景区名称查询景点簇并追加到 enhanced_results。
        返回 (更新后的文本, 是否找到景点数据)。"""
        scenic_aids, attraction_names = await self._get_scenic_attraction_ids_and_names(scenic_name)
        if not scenic_aids:
            return enhanced_results, False
        ctx = enhanced_results
        if attraction_names and "根据图数据库，景区「" not in ctx:
            sentence = self._format_scenic_attractions_sentence(scenic_name, attraction_names)
            if sentence:
                ctx = sentence + "\n\n" + ctx
        clusters_ctx = await self._get_attraction_cluster_context(scenic_aids, max_items=max_attractions)
        if clusters_ctx:
            if intent == QueryIntent.ROUTE:
                ctx = ctx + "\n\n【路线可选景点】\n" + clusters_ctx
            else:
                ctx = ctx + "\n\n" + clusters_ctx
        return ctx, True

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
        s_ticket_info = ""
        s_opening_hours = ""
        s_transport_info = ""
        s_service_facilities = ""
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
                    s_ticket_info = (s.get("ticket_info") or "").strip()
                    s_opening_hours = (s.get("opening_hours") or "").strip()
                    s_transport_info = (s.get("transport_info") or "").strip()
                    s_service_facilities = (s.get("service_facilities") or "").strip()
                elif isinstance(s, dict):
                    s_name = (s.get("name") or (s.get("properties") or {}).get("name") or "").strip()
                    s_area = (s.get("area") or (s.get("properties") or {}).get("area") or "").strip()
                    s_location = (s.get("location") or (s.get("properties") or {}).get("location") or "").strip()
                    props = s.get("properties") or {}
                    s_ticket_info = (s.get("ticket_info") or props.get("ticket_info") or "").strip()
                    s_opening_hours = (s.get("opening_hours") or props.get("opening_hours") or "").strip()
                    s_transport_info = (s.get("transport_info") or props.get("transport_info") or "").strip()
                    s_service_facilities = (s.get("service_facilities") or props.get("service_facilities") or "").strip()
            if rel_type and n is not None:
                n_name = self._get_node_name(n)
                if not n_name:
                    continue
                if rel_type == "HAS_SPOT":
                    # 只收录有 id 的 Attraction 节点（来自数据库），
                    # 过滤掉纯文本提取的 :Spot 名称节点（无 id），避免显示未录入的景点
                    n_id = None
                    if hasattr(n, 'get'):
                        n_id = n.get('id')
                    elif isinstance(n, dict):
                        n_id = n.get('id') or (n.get('properties') or {}).get('id')
                    if n_id is not None:
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
        if s_ticket_info:
            lines.append(f"门票与优惠：{s_ticket_info}")
        if s_opening_hours:
            lines.append(f"开放时间：{s_opening_hours}")
        if s_transport_info:
            lines.append(f"交通信息：{s_transport_info}")
        if s_service_facilities:
            lines.append(f"服务设施：{s_service_facilities}")
        if spot_names:
            lines.append("下属景点：" + "、".join(spot_names[:20]))
        if feature_names:
            lines.append("特色：" + "、".join(feature_names[:15]))
        if honor_names:
            lines.append("荣誉：" + "、".join(honor_names[:10]))
        return "【景区一簇信息】\n" + "\n".join(lines)

    async def _get_scenic_spot_cluster_context_impl(
        self, *, scenic_spot_id: Optional[int] = None, scenic_name: Optional[str] = None
    ) -> str:
        """按 id 或 name 拉取景区一簇（内部共用，避免重复 Cypher/executor 逻辑）。"""
        if scenic_spot_id is not None:
            query = "MATCH (s:ScenicSpot {scenic_spot_id: $sid}) OPTIONAL MATCH (s)-[r]->(n) RETURN s, type(r) as rel_type, n"
            params: Dict[str, Any] = {"sid": int(scenic_spot_id)}
        elif scenic_name and str(scenic_name).strip():
            query = "MATCH (s:ScenicSpot {name: $name}) OPTIONAL MATCH (s)-[r]->(n) RETURN s, type(r) as rel_type, n"
            params = {"name": str(scenic_name).strip()}
        else:
            return ""
        try:
            loop = asyncio.get_event_loop()
            rows = await loop.run_in_executor(
                None, neo4j_client.execute_query, query, params
            )
            return self._parse_scenic_spot_rows(rows or [])
        except Exception as e:
            logger.warning("拉取景区簇失败 %s: %s", "sid=%s" % scenic_spot_id if scenic_spot_id is not None else "name=%s" % scenic_name, e)
            return ""

    async def _get_scenic_spot_cluster_context(self, scenic_spot_id: int) -> str:
        """按 scenic_spot_id 拉取景区一簇（异步）。"""
        return await self._get_scenic_spot_cluster_context_impl(scenic_spot_id=scenic_spot_id)

    async def _get_scenic_spot_cluster_context_by_name(self, scenic_name: str) -> str:
        """按景区名称拉取景区一簇（兼容无 scenic_spot_id 的旧节点，异步）。"""
        return await self._get_scenic_spot_cluster_context_impl(scenic_name=(scenic_name or "").strip() or None)

    async def _get_scenic_spot_cluster_by_entity_name(self, entity_name: str) -> str:
        """按实体名在图库中查 ScenicSpot（name 匹配），再拉取景区一簇；未找到返回空串。用于指代/实体名补全。"""
        if not (entity_name or "").strip():
            return ""
        try:
            loop = asyncio.get_event_loop()
            rows = await loop.run_in_executor(
                None,
                neo4j_client.execute_query,
                "MATCH (s:ScenicSpot {name: $name}) RETURN s.scenic_spot_id AS sid, s.name AS s_name LIMIT 1",
                {"name": (entity_name or "").strip()},
            )
            if not rows:
                return ""
            r0 = rows[0]
            sid, s_name = r0.get("sid"), r0.get("s_name")
            if sid is not None:
                return await self._get_scenic_spot_cluster_context_impl(scenic_spot_id=int(sid))
            if s_name:
                return await self._get_scenic_spot_cluster_context_impl(scenic_name=str(s_name).strip())
        except Exception as e:
            logger.warning("从实体名称查找景区失败: %s", e)
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

    def _build_scored_context(
        self,
        *,
        vector_results: List[Dict[str, Any]],
        graph_results: List[Dict[str, Any]],
        entity_names: List[str],
        resolved_entities: List[str],
        scenic_name: str,
        alpha: float = DEFAULT_FUSION_ALPHA,
        beta: float = DEFAULT_FUSION_BETA,
        gamma: float = DEFAULT_FUSION_GAMMA,
        budget_chars: int = DEFAULT_CONTEXT_BUDGET_CHARS,
    ) -> tuple[str, List[Dict[str, Any]]]:
        """
        S(c)=α svec(c)+β sgraph(c)+γ sent(c)
        - svec: 来自向量检索 score（已由 distance 换算）
        - sgraph: 图检索命中实体在候选片段中的出现比例（启发式归一化）
        - sent: 候选片段与当前景区/消解实体的字符串匹配分
        """
        a = float(alpha)
        b = float(beta)
        g = float(gamma)
        ssum = a + b + g
        if ssum <= 0:
            a, b, g = 1.0, 0.0, 0.0
        else:
            a, b, g = a / ssum, b / ssum, g / ssum

        budget = max(400, int(budget_chars or DEFAULT_CONTEXT_BUDGET_CHARS))
        scenic_name = (scenic_name or "").strip()
        resolved = [str(x).strip() for x in (resolved_entities or []) if str(x).strip()]
        entities = [str(x).strip() for x in (entity_names or []) if str(x).strip()]

        rel_pairs: List[tuple[str, str]] = []
        for r in graph_results or []:
            try:
                a_node = r.get("a") if isinstance(r, dict) else None
                b_node = r.get("b") if isinstance(r, dict) else None
                a_name = (a_node.get("name") if hasattr(a_node, "get") else "") if a_node is not None else ""
                b_name = (b_node.get("name") if hasattr(b_node, "get") else "") if b_node is not None else ""
                a_name = str(a_name).strip()
                b_name = str(b_name).strip()
                if a_name or b_name:
                    rel_pairs.append((a_name, b_name))
            except Exception:
                continue

        scored: List[Dict[str, Any]] = []
        for item in vector_results or []:
            c = dict(item)
            content = (c.get("content") or "").strip()
            svec = float(c.get("score") or 0.0)

            hits = 0
            if content and rel_pairs:
                for an, bn in rel_pairs:
                    if an and an in content:
                        hits += 1
                    if bn and bn in content:
                        hits += 1
            # 除数取 max(3, 实际关系对数×2)，避免关系多时分数被钳制在 1.0 失去区分度
            sgraph = min(1.0, hits / max(3, len(rel_pairs) * 2)) if hits > 0 else 0.0

            sent = 0.0
            if content:
                if scenic_name and scenic_name in content:
                    sent = 1.0
                else:
                    for e0 in resolved:
                        if e0 and e0 in content:
                            sent = 1.0
                            break
                if sent <= 0 and entities:
                    for e1 in entities[:5]:
                        if e1 and e1 in content:
                            sent = 0.5
                            break

            S = a * svec + b * sgraph + g * sent
            c["svec"] = svec
            c["sgraph"] = sgraph
            c["sent"] = sent
            c["S"] = S
            scored.append(c)

        scored.sort(key=lambda x: float(x.get("S") or 0.0), reverse=True)

        context_parts: List[str] = []
        if scored:
            context_parts.append("相关文本内容：")
            used = 0
            idx = 1
            for c in scored:
                content = (c.get("content") or "").strip()
                text_id = (c.get("text_id") or "").strip()
                svec = float(c.get("svec") or 0.0)
                sgraph = float(c.get("sgraph") or 0.0)
                sent = float(c.get("sent") or 0.0)
                S = float(c.get("S") or 0.0)
                header = f"{idx}. (S: {S:.2f}, svec: {svec:.2f}, sgraph: {sgraph:.2f}, sent: {sent:.2f})"
                block = f"{header}\n{content}" if content else f"{header}\n{text_id}"
                block_len = len(block)
                if used + block_len > budget:
                    break
                context_parts.append(block)
                used += block_len
                idx += 1

        if graph_results:
            context_parts.append("\n相关实体关系：")
            seen_relations = set()
            for r in graph_results[:8]:
                if isinstance(r, dict) and "a" in r and "b" in r and "rel_type" in r:
                    try:
                        a_name = r["a"].get("name", "未知")
                        b_name = r["b"].get("name", "未知")
                        rel_type = r.get("rel_type", "相关")
                        relation_key = f"{a_name}-{rel_type}-{b_name}"
                        if relation_key in seen_relations:
                            continue
                        seen_relations.add(relation_key)
                        context_parts.append(f"- {a_name} {rel_type} {b_name}")
                    except Exception:
                        continue

        if entity_names:
            context_parts.append(f"\n识别到的实体：{', '.join(entity_names[:5])}")

        return "\n".join(context_parts), scored
    
    async def generate_answer(
        self, 
        query: str, 
        context: Optional[str] = None, 
        use_rag: bool = True,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        character_prompt: Optional[str] = None,
        scenic_name: Optional[str] = None,
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
            rag_results = await self.hybrid_search(
                query,
                top_k=5,
                conversation_history=conversation_history,
                scenic_name=scenic_name,
            )
            primary_attraction_id = rag_results.get("primary_attraction_id")
            out_context = rag_results.get("enhanced_context", "") or ""
            detected_intent = rag_results.get("intent")
            already_has_list = "根据图数据库，景区「" in (out_context or "")
            if detected_intent == "listing" and not already_has_list:
                scenic_ctx = await self._build_scenic_attractions_context(
                    query=query,
                    rag_results=rag_results,
                    conversation_history=conversation_history,
                    scenic_name=scenic_name,
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
                "intent": rag_results.get("intent"),
                "strategy": rag_results.get("strategy"),
            }
        if character_prompt:
            system_prompt = f"{RAG_BASE_SYSTEM_PROMPT}\n\n角色设定：{character_prompt}"
        else:
            system_prompt = RAG_BASE_SYSTEM_PROMPT
        messages = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            messages.extend(conversation_history)
        intent_hint = ""
        if use_rag and rag_debug:
            detected_intent = rag_debug.get("intent") or (await self._classify_query_intent(query)).value
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
{intent_hint}以下是从知识库检索到的相关信息，请严格依据这些内容作答，不得引用知识库以外的信息：

{out_context if out_context else "知识库中暂无相关信息，请如实告知游客。"}

请用口语化中文回答游客的问题。"""
        messages.append({"role": "user", "content": user_prompt})
        if rag_debug is not None:
            rag_debug["final_sent_to_llm"] = user_prompt

        try:
            response = await asyncio.to_thread(
                self.llm_client.chat.completions.create,
                model=settings.OPENAI_MODEL,
                messages=messages,
                temperature=0.3,
                max_tokens=1000,
            )
            
            answer = response.choices[0].message.content
            if answer:
                answer = re.sub(r"编号为\s*kb_\d+", "", answer)
                answer = re.sub(r"\bkb_\d+\b", "", answer)
                answer = re.sub(r"\s{2,}", " ", answer).strip()
            if answer:
                answer = _strip_emoji(answer)
                answer = _clean_special_symbols(answer)

            async def _write_rag_log():
                try:
                    log_root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
                    os.makedirs(log_root, exist_ok=True)
                    log_path = os.path.join(log_root, "rag_context.log")
                    entry = {
                        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                        "query": query,
                        "character_prompt": character_prompt,
                        "use_rag": use_rag,
                        "rag_debug": rag_debug,
                        "final_answer_preview": answer[:2000] if answer else "",
                    }

                    def _io_task():
                        try:
                            with open(log_path, "a", encoding="utf-8") as f:
                                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                            try:
                                with open(log_path, "r", encoding="utf-8") as f:
                                    lines = [ln for ln in f.readlines() if ln.strip()]
                                if len(lines) > 20:
                                    with open(log_path, "w", encoding="utf-8") as f:
                                        f.writelines(lines[-20:])
                            except Exception:
                                pass
                        except Exception as e:
                            logger.warning(f"Failed to write RAG context log: {e}")

                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, _io_task)
                except Exception as e:
                    logger.warning(f"Failed to schedule RAG context log write: {e}")

            try:
                asyncio.create_task(_write_rag_log())
            except RuntimeError:
                # 无事件循环时退回同步写入
                try:
                    log_root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
                    os.makedirs(log_root, exist_ok=True)
                    log_path = os.path.join(log_root, "rag_context.log")
                    entry = {
                        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                        "query": query,
                        "character_prompt": character_prompt,
                        "use_rag": use_rag,
                        "rag_debug": rag_debug,
                        "final_answer_preview": answer[:2000] if answer else "",
                    }
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                except Exception as e:
                    logger.warning(f"Fallback write RAG context log failed: {e}")

            logger.info(f"Generated answer for query: {query[:50]}...")
            return {"answer": answer, "primary_attraction_id": primary_attraction_id, "context": out_context}
        except Exception as e:
            logger.error(f"Failed to generate answer: {e}")
            return {"answer": f"抱歉，生成回答时出现错误：{str(e)}", "primary_attraction_id": None, "context": out_context}


rag_service = RAGService()

