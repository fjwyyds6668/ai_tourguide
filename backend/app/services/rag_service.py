"""GraphRAG 检索服务：图数据库 + 向量检索增强生成"""
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

RELEVANCE_SCORE_THRESHOLD = 0.2  # 向量相似度下限，低于此值视为不相关

def _strip_emoji(text: str) -> str:
    """去掉表情与末尾控制字符，避免 TTS 异常；缺句尾时补句号。"""
    if not text or not isinstance(text, str):
        return text or ""
    # 说明：
    # - 旧实现只覆盖到 U+1F9FF，像 🫶(U+1FAF6) 这种新 emoji 会漏掉
    # - 同时清掉一些常见“装饰符号”（如全角波浪线 ～ / 波浪线 ~），避免影响展示与 TTS
    s = re.sub(
        r"[\u2600-\u26FF\u2700-\u27BF"
        r"\U0001F300-\U0001F9FF"
        r"\U0001FA00-\U0001FAFF"  # newer emoji blocks (e.g., 🫶)
        r"]",
        "",
        text,
    )
    # 装饰性波浪线：~ / ～(FF5E) / 〜(301C)
    s = re.sub(r"[~\uFF5E\u301C]", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    s = re.sub(r"[\s\u200b\u200c\u200d\ufeff\r\n]+$", "", s)
    if s and s[-1] not in "。！？.!?…":
        s = s.rstrip("，、；：") + "。"
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
        self._init_embedding_model()
        self._init_ner()
        self._init_llm_client()

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
            self.embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            logger.info("Embedding model loaded")
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
        # 过滤掉无意义的通用词
        stop_words = {"这里", "那里", "哪些", "什么", "这个", "那个", "景点", "景区", "地方", 
                      "attraction", "scenic", "spot", "这里有哪些", "有哪些景点", "景点都有"}
        entities = []
        if JIEBA_AVAILABLE:
            words = pseg.cut(text)
            for word, flag in words:
                # 过滤：长度>=2，不是停用词，且是地名/人名/机构名/其他专名，或长度>=3的词汇
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
        """向量相似度搜索。"""
        if not milvus_client.connected:
            milvus_client.connect()
        try:
            collection = milvus_client.create_collection_if_not_exists(
                collection_name, dimension=384, load=False
            )
        except Exception as e:
            logger.warning(f"Milvus not available for vector search, fallback to empty results: {e}")
            return []
        try:
            from pymilvus import utility
            if not utility.has_collection(collection_name):
                logger.warning(f"Collection '{collection_name}' does not exist")
                return []
        except Exception as e:
            logger.warning(f"Failed to check collection existence: {e}")
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
                    logger.info(f"Collection '{collection_name}' is not loaded (state: {load_state}), loading now...")
                    collection.load()
                self._milvus_loaded_collections.add(collection_name)
            except Exception as e:
                logger.warning(f"Failed to ensure collection '{collection_name}' loaded, will rely on retry: {e}")
        query_vector = [self.generate_embedding(query)]
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
        search_results = []
        if results and len(results) > 0:
            for hit in results[0]:
                search_results.append({
                    "id": hit.id,
                    "text_id": hit.entity.get("text_id", ""),
                    "distance": hit.distance,
                    "score": 1 / (1 + hit.distance) if hit.distance > 0 else 1.0,
                })
        
        return search_results
    
    async def graph_search(self, entity_name: str, relation_type: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """图数据库关系查询。relation_type 白名单校验后拼接，避免注入。"""
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
        results = neo4j_client.execute_query(query, {"entities": entities})
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
        # 同时覆盖“有哪些景点”和“有多少个景点/几个景点”这两类意图
        pattern = (
            r"有哪些景点|景点都有(什么|哪些)|景点情况|景点分布|有什么景点|景点.*有哪些"
            r"|有多少个景点|多少个景点|景点有多少个|景区有多少个景点|几个景点"
        )
        return bool(re.search(pattern, q))

    def _get_scenic_spot_by_attraction_id(self, attraction_id: int) -> Optional[Dict[str, Any]]:
        """通过景点 id 反查所属景区，返回 {'sid', 's_name'} 或 None。"""
        try:
            query = """
            MATCH (a:Attraction {id: $aid})
            OPTIONAL MATCH (a)-[:属于]->(s1:ScenicSpot)
            OPTIONAL MATCH (s2:ScenicSpot)-[:HAS_SPOT]->(a)
            WITH a, coalesce(s1, s2) AS s WHERE s IS NOT NULL
            RETURN s.scenic_spot_id AS sid, s.name AS s_name
            LIMIT 1
            """
            rows = neo4j_client.execute_query(query, {"aid": int(attraction_id)})
            if rows:
                row0 = rows[0]
                return {
                    "sid": row0.get("sid"),
                    "s_name": row0.get("s_name"),
                }
        except Exception as e:
            logger.warning(f"_get_scenic_spot_by_attraction_id failed attraction_id={attraction_id}: {e}")
        return None

    def _get_scenic_attractions_sentence_by_name(self, scenic_name: str) -> str:
        """根据景区名称查询其下相关景点，并格式化为一句话描述（带数量信息）。"""
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
            rows = neo4j_client.execute_query(scenic_attractions_q, {"name": scenic_name}) or []
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
        """向量检索 + 实体识别 + 图检索 + 结果融合（并行优化）。"""
        vector_results = await self.vector_search(query, top_k=top_k)
        vector_results_relevant = [r for r in (vector_results or []) if (r.get("score") or 0) >= RELEVANCE_SCORE_THRESHOLD]
        if not vector_results_relevant and vector_results:
            vector_results_relevant = vector_results[:1]
        vector_results = vector_results_relevant

        # 批量提取实体，减少重复处理
        texts_to_extract = [query]
        if vector_results:
            text_ids = [r.get("text_id", "") for r in vector_results[:3] if r.get("text_id")]
            texts_to_extract.extend(text_ids)
        
        # 并行提取实体（如果文本较多）
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
        
        # 使用字典去重，保留最高置信度
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
        
        tasks = []
        if entity_names:
            tasks.extend([self.graph_search(name, limit=5) for name in entity_names[:5]])
            if len(entity_names) > 1:
                tasks.append(self.graph_subgraph_search(entity_names[:3], depth=2))
        
        graph_results = []
        subgraph_data = None
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            task_idx = 0
            for name in entity_names[:5]:
                if task_idx < len(results):
                    r = results[task_idx]
                    if not isinstance(r, Exception):
                        graph_results.extend(r)
                    task_idx += 1
            if len(entity_names) > 1 and task_idx < len(results):
                r = results[task_idx]
                if not isinstance(r, Exception):
                    subgraph_data = r
        
        # 并行执行文本内容获取（使用线程池避免阻塞）
        text_contents = {}
        if text_ids_to_fetch:
            loop = asyncio.get_event_loop()
            text_contents = await loop.run_in_executor(
                None, 
                self._get_text_contents_from_neo4j, 
                text_ids_to_fetch
            )
        
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
        
        # 检测列举类查询（"有哪些景点"），主动查询景区下的所有景点
        is_listing_query = self._is_listing_query(query)
        if is_listing_query and primary_attraction_id is not None:
            # 通过找到的景点反查所属景区
            try:
                parent_info = self._get_scenic_spot_by_attraction_id(primary_attraction_id)
                if parent_info:
                    s_name = parent_info.get("s_name")
                    if s_name:
                        # 先拉取该景区下所有景点的 id（用于拼“所有景点簇”）
                        scenic_aids: List[int] = []
                        try:
                            scenic_aids_q = """
                            MATCH (s:ScenicSpot {name: $name})
                            OPTIONAL MATCH (s)<-[:属于]-(a:Attraction)
                            OPTIONAL MATCH (s)-[:HAS_SPOT]->(a2:Attraction)
                            WITH collect(DISTINCT a) + collect(DISTINCT a2) AS xs
                            UNWIND xs AS x
                            WITH DISTINCT x WHERE x IS NOT NULL AND x.id IS NOT NULL
                            RETURN x.id AS aid
                            ORDER BY aid
                            LIMIT 200
                            """
                            rows = neo4j_client.execute_query(scenic_aids_q, {"name": str(s_name).strip()}) or []
                            for rr in rows:
                                if rr and rr.get("aid") is not None:
                                    try:
                                        scenic_aids.append(int(rr["aid"]))
                                    except Exception:
                                        continue
                        except Exception as e:
                            logger.warning(f"查询景区下景点id失败: {e}")
                        sentence = self._get_scenic_attractions_sentence_by_name(str(s_name).strip())
                        if sentence:
                            enhanced_results = sentence + "\n\n" + (enhanced_results or "")

                        # 列举类问题：尽量把“该景区下的所有景点簇信息”也拼进去
                        if scenic_aids:
                            clusters_ctx = await self._get_attraction_cluster_context(scenic_aids, max_items=30)
                            if clusters_ctx:
                                enhanced_results = (enhanced_results or "") + "\n\n" + clusters_ctx
            except Exception as e:
                logger.warning(f"列举查询时查询景区景点失败: {e}")
        query_about_scenic = bool(re.search(r"什么景区|哪个景区|是啥景区|这是什么景区|是哪个景区|啥景区|哪个景点.*景区|介绍.*景区|景区.*介绍|这个景区", (query or "").strip()))
        scenic_ctx_found = False
        if query_about_scenic:
            scenic_tasks = []
            if primary_attraction_id is not None:
                async def get_scenic_from_attraction():
                    try:
                        parent_info = self._get_scenic_spot_by_attraction_id(primary_attraction_id)
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
                        scenic_rows = neo4j_client.execute_query(scenic_check_q, {"name": name})
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
        # 列举类查询通常已拼接“多个景点簇”，这里不再补 primary 单簇，避免重复
        is_listing_query = self._is_listing_query(query)
        if primary_attraction_id is not None and (not is_listing_query) and not (query_about_scenic and scenic_ctx_found):
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
                        res = neo4j_client.execute_query(check_q, {"name": cand})
                        if res and isinstance(res, list) and res[0].get("name"):
                            scenic_names.add(res[0]["name"])
                    except Exception:
                        continue
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
        parts: List[str] = []
        for scenic_name in list(scenic_names)[:3]:
            sentence = self._get_scenic_attractions_sentence_by_name(scenic_name)
            if sentence:
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
        """从 Neo4j 拉取景点一簇（属性+出边），格式化为文本供 LLM（并行优化）。

        max_items: 为避免一次性塞入过多簇导致上下文截断，做安全上限（列举类问题建议 20 左右）。
        """
        if not attraction_ids:
            return ""
        
        # 并行查询多个景点
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
        
        # 并行获取所有景点簇
        # 去重 + 截断（保序）
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
        """按 scenic_spot_id 拉取景区一簇。"""
        try:
            query = """
            MATCH (s:ScenicSpot {scenic_spot_id: $sid})
            OPTIONAL MATCH (s)-[r]->(n)
            RETURN s, type(r) as rel_type, n
            """
            rows = neo4j_client.execute_query(query, {"sid": int(scenic_spot_id)})
            return self._parse_scenic_spot_rows(rows or [])
        except Exception as e:
            logger.warning(f"拉取景区簇失败 scenic_spot_id={scenic_spot_id}: {e}")
            return ""

    async def _get_scenic_spot_cluster_context_by_name(self, scenic_name: str) -> str:
        """按景区名称拉取景区一簇（兼容无 scenic_spot_id 的旧节点）。"""
        if not (scenic_name or "").strip():
            return ""
        try:
            query = """
            MATCH (s:ScenicSpot {name: $name})
            OPTIONAL MATCH (s)-[r]->(n)
            RETURN s, type(r) as rel_type, n
            """
            rows = neo4j_client.execute_query(query, {"name": (scenic_name or "").strip()})
            return self._parse_scenic_spot_rows(rows or [])
        except Exception as e:
            logger.warning(f"拉取景区簇失败（按名称） scenic_name={scenic_name}: {e}")
            return ""

    def _get_text_contents_from_neo4j(self, text_ids: List[str]) -> Dict[str, str]:
        """按 text_id 从 Neo4j Text 节点拉取正文。"""
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
            # 检测列举类查询，主动补充景区下的所有景点信息
            if self._is_listing_query(query):
                scenic_ctx = await self._build_scenic_attractions_context(
                    query=query,
                    rag_results=rag_results,
                    conversation_history=conversation_history,
                )
                # 避免重复（hybrid_search 可能已经拼过“根据图数据库…”）
                already_has_list = "根据图数据库，景区「" in (out_context or "")
                if scenic_ctx and not already_has_list:
                    out_context = f"{out_context}\n\n{scenic_ctx}" if out_context else scenic_ctx
                # 如果还没有找到景区信息，尝试从 primary_attraction_id 反查
                elif rag_results.get("primary_attraction_id") is not None and not already_has_list:
                    try:
                        aid = rag_results.get("primary_attraction_id")
                        parent_info = self._get_scenic_spot_by_attraction_id(aid)
                        scenic_name = parent_info.get("s_name") if parent_info else None
                        if scenic_name:
                            scenic_ctx = self._get_scenic_attractions_sentence_by_name(str(scenic_name).strip())
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
        user_prompt = f"""用户问题：{query}

上下文信息：
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

