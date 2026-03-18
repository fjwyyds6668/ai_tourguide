"""GraphRAG 检索 API"""
import base64
import logging
import asyncio
import json
import os
import time
import threading
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple
from app.services.rag_service import rag_service, _clean_special_symbols, RAG_BASE_SYSTEM_PROMPT
from app.services.session_service import session_service
from app.services.voice_service import voice_service
from app.api.voice import _normalize_tts_text
from app.core.prisma_client import get_prisma
from app.core.config import settings
from app.models.interaction import Interaction

logger = logging.getLogger(__name__)

router = APIRouter()

_HISTORY_BUDGET_CHARS = 1200  # 发送给LLM前的对话历史字符预算（仅裁剪历史，不含本轮问题）
MAX_RECENT_HISTORY = 20  # 裁剪前保留的最近消息条数


def _trim_conversation_history(
    history: List[Dict[str, str]],
    *,
    budget_chars: int = _HISTORY_BUDGET_CHARS,
    prefer_terms: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """按"最近几轮+长度预算"裁剪会话历史，优先保留包含关键实体的消息。"""
    if not history:
        return []
    budget = max(0, int(budget_chars or 0))
    if budget <= 0:
        return []

    terms = [t.strip() for t in (prefer_terms or []) if isinstance(t, str) and t.strip()]

    def _len_msg(m: Dict[str, str]) -> int:
        return len((m.get("role") or "")) + len((m.get("content") or ""))

    def _hit(m: Dict[str, str]) -> bool:
        if not terms:
            return False
        c = (m.get("content") or "")
        return any(t in c for t in terms)

    recent = [m for m in history if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
    recent = recent[-MAX_RECENT_HISTORY:]
    flags = [_hit(m) for m in recent]

    keep: set[int] = set()
    used = 0
    for i in range(len(recent) - 1, -1, -1):
        if not flags[i]:
            continue
        ln = _len_msg(recent[i])
        if used + ln > budget:
            continue
        keep.add(i)
        used += ln
    for i in range(len(recent) - 1, -1, -1):
        if i in keep:
            continue
        ln = _len_msg(recent[i])
        if used + ln > budget:
            continue
        keep.add(i)
        used += ln
    return [recent[i] for i in range(len(recent)) if i in keep]

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5

class QueryResponse(BaseModel):
    vector_results: List[Dict[str, Any]]
    graph_results: List[Dict[str, Any]]
    query: str

class GenerateRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    character_id: Optional[int] = None
    use_rag: bool = True
    scenic_name: Optional[str] = None

class GenerateResponse(BaseModel):
    answer: str
    query: str
    context: str = ""
    session_id: str


def _resolve_session_id(request: GenerateRequest) -> str:
    if request.session_id:
        session = session_service.get_session(request.session_id)
        if session:
            return request.session_id
    return session_service.create_session(request.character_id)


async def _load_character_prompt_and_voice(character_id: Optional[int]) -> Tuple[Optional[str], Optional[str]]:
    if not character_id:
        return None, None
    try:
        prisma = await get_prisma()
        character = await prisma.character.find_unique(where={"id": character_id})
        if not character:
            return None, None
        prompt = character.prompt if character.prompt else None
        voice = character.voice if character.voice else settings.XFYUN_VOICE
        return prompt, voice
    except Exception as e:
        logger.error("Failed to load character: %s", e)
        return None, None


# 景点名匹配缓存 60s
_attraction_id_name_cache: Optional[List[Tuple[int, str]]] = None
_attraction_cache_time: float = 0
_ATTRACTION_CACHE_TTL = 60.0
_attraction_cache_lock = threading.Lock()  # _save_interaction 在线程池中执行，需加锁保护全局缓存


def _get_attraction_id_name_list() -> List[Tuple[int, str]]:
    global _attraction_id_name_cache, _attraction_cache_time
    now = time.time()
    with _attraction_cache_lock:
        if _attraction_id_name_cache is not None and (now - _attraction_cache_time) < _ATTRACTION_CACHE_TTL:
            return _attraction_id_name_cache
        from app.core.database import SessionLocal
        from app.models.attraction import Attraction as AttractionModel
        db_local = SessionLocal()
        try:
            rows = (
                db_local.query(AttractionModel.id, AttractionModel.name)
                .filter(AttractionModel.id.isnot(None), AttractionModel.name.isnot(None), AttractionModel.name != "")
                .limit(200)
                .all()
            )
            out = [(int(row[0]), str(row[1])) for row in rows if row[0] is not None]
            _attraction_id_name_cache = out
            _attraction_cache_time = now
            return out
        finally:
            db_local.close()


def _save_interaction(
    session_id: str,
    character_id: Optional[int],
    query_text: str,
    response_text: str,
    primary_attraction_id: Optional[int],
    scenic_name: Optional[str] = None,
    interaction_type: str = "voice_query",
) -> None:
    try:
        from app.core.database import SessionLocal
        from app.core.neo4j_client import neo4j_client
        db_local = SessionLocal()
        try:
            aid = primary_attraction_id
            if aid is None:
                q = (query_text or "").strip()
                r = (response_text or "").strip()
                scenic = (scenic_name or "").strip()

                wq, wr, ws = 1.0, 0.6, 0.8

                best_id: Optional[int] = None
                best_score: float = 0.0

                scenic_aid_set: set[int] = set()
                if scenic:
                    try:
                        rows = neo4j_client.execute_query(
                            """
                            MATCH (s:ScenicSpot {name: $s_name})
                            OPTIONAL MATCH (s)<-[:属于]-(a1:Attraction)
                            OPTIONAL MATCH (s)-[:HAS_SPOT]->(a2:Attraction)
                            WITH collect(DISTINCT a1.id) + collect(DISTINCT a2.id) AS xs
                            UNWIND xs AS aid
                            WITH DISTINCT aid WHERE aid IS NOT NULL
                            RETURN aid
                            LIMIT 800
                            """,
                            {"s_name": scenic},
                        ) or []
                        scenic_aid_set = {int(x["aid"]) for x in rows if x and x.get("aid") is not None}
                    except Exception:
                        scenic_aid_set = set()

                for rid, name in _get_attraction_id_name_list():
                    nm = (name or "").strip()
                    if not nm:
                        continue
                    cnt_q = q.count(nm) if q else 0
                    cnt_r = r.count(nm) if r else 0
                    if cnt_q == 0 and cnt_r == 0:
                        continue

                    scenic_hit = 0
                    if scenic and scenic_aid_set:
                        try:
                            scenic_hit = 1 if int(rid) in scenic_aid_set else 0
                        except Exception:
                            scenic_hit = 0

                    score = wq * cnt_q + wr * cnt_r + ws * scenic_hit
                    if score > best_score:
                        best_score = score
                        best_id = int(rid)

                if best_id is not None and best_score > 0:
                    aid = best_id
            interaction = Interaction(
                session_id=session_id,
                character_id=character_id,
                query_text=query_text,
                response_text=response_text,
                interaction_type=interaction_type,
                attraction_id=aid,
            )
            db_local.add(interaction)
            db_local.commit()
        finally:
            db_local.close()
    except Exception as e:
        logger.error("Failed to save interaction: %s", e)


@router.post("/search", response_model=QueryResponse)
async def hybrid_search(request: QueryRequest):
    try:
        results = await rag_service.hybrid_search(request.query, top_k=request.top_k)
        return QueryResponse(**results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/vector-search")
async def vector_search(request: QueryRequest):
    try:
        results = await rag_service.vector_search(request.query, top_k=request.top_k)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/graph-search")
async def graph_search(entity_name: str, relation_type: str = None, limit: int = 10):
    try:
        results = await rag_service.graph_search(entity_name, relation_type, limit)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate", response_model=GenerateResponse)
async def generate_answer(request: GenerateRequest, background_tasks: BackgroundTasks):
    try:
        session_id = _resolve_session_id(request)
        (character_prompt, _), conversation_history = await asyncio.gather(
            _load_character_prompt_and_voice(request.character_id),
            asyncio.to_thread(session_service.get_conversation_history, session_id),
        )
        conversation_history = _trim_conversation_history(
            conversation_history,
            budget_chars=_HISTORY_BUDGET_CHARS,
            prefer_terms=[request.scenic_name] if request.scenic_name else None,
        )

        result = await rag_service.generate_answer(
            query=request.query,
            context=None,
            use_rag=request.use_rag,
            conversation_history=conversation_history,
            character_prompt=character_prompt,
            scenic_name=request.scenic_name,
        )
        answer = result["answer"]
        context = result.get("context", "")
        primary_attraction_id = result.get("primary_attraction_id")

        session_service.add_message(session_id, "user", request.query)
        session_service.add_message(session_id, "assistant", answer)

        background_tasks.add_task(
            _save_interaction,
            session_id,
            request.character_id,
            request.query,
            answer,
            primary_attraction_id,
            request.scenic_name,
            "text_query",
        )

        return GenerateResponse(
            answer=answer,
            query=request.query,
            context=context,
            session_id=session_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate-stream")
async def generate_answer_stream(request: GenerateRequest, background_tasks: BackgroundTasks):
    async def generate_stream() -> AsyncGenerator[str, None]:
        stream_future = None
        session_id = _resolve_session_id(request)
        yield f"data: {json.dumps({'type': 'session_id', 'content': session_id}, ensure_ascii=False)}\n\n"
        if not rag_service.llm_client:
            yield f"data: {json.dumps({'type': 'error', 'content': 'AI服务未配置'}, ensure_ascii=False)}\n\n"
            return

        (character_prompt, voice), conversation_history = await asyncio.gather(
            _load_character_prompt_and_voice(request.character_id),
            asyncio.to_thread(session_service.get_conversation_history, session_id),
        )
        conversation_history = _trim_conversation_history(
            conversation_history,
            budget_chars=_HISTORY_BUDGET_CHARS,
            prefer_terms=[request.scenic_name] if request.scenic_name else None,
        )
        if not voice:
            voice = settings.XFYUN_VOICE
        
        rag_results = None
        primary_attraction_id = None
        context = ""
        if request.use_rag:
            needs_context = rag_service._query_needs_context(request.query)
            if not needs_context:
                context = "当前问题无需知识库上下文，请自然、简短回复。"
            else:
                try:
                    rag_results = await rag_service.hybrid_search(
                        request.query,
                        top_k=5,
                        conversation_history=conversation_history,
                        scenic_name=request.scenic_name,
                    )
                    primary_attraction_id = rag_results.get("primary_attraction_id")
                    context = rag_results.get("enhanced_context", "") or ""
                except Exception as e:
                    logger.error(f"RAG search failed: {e}")
                    rag_results = {"errors": {"rag_search": str(e)}}
        
        if character_prompt:
            system_prompt = f"{RAG_BASE_SYSTEM_PROMPT}\n\n角色设定：{character_prompt}"
        else:
            system_prompt = RAG_BASE_SYSTEM_PROMPT

        backend_tts_enabled = bool(settings.XFYUN_APPID and settings.XFYUN_API_KEY)
        
        messages = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            messages.extend(conversation_history)
        
        user_prompt = f"""用户问题：{request.query}
上下文信息：
{context if context else "无额外上下文信息"}

请基于以上信息回答用户的问题。"""
        messages.append({"role": "user", "content": user_prompt})

        full_answer = ""
        _interaction_saved = False
        try:
            stream = rag_service.llm_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
                stream=True
            )

            prev_content: str = ""
            accumulated_text = ""
            completed_audio: Dict[int, str] = {}
            fallback_tts: Dict[int, str] = {}
            next_audio_idx = 0
            tts_chunk_index = [0]
            Lmin = 12
            TTS_SENTENCE_TIMEOUT = settings.XFYUN_TTS_TIMEOUT
            TTS_MAX_CONCURRENCY = 3
            tts_sema = asyncio.Semaphore(TTS_MAX_CONCURRENCY)
            TTS_MAX_PENDING = 10
            pending_tts = 0
            SENTENCE_PUNCT = ['。', '！', '？', '.', '!', '?']
            
            def _compute_cut(buf: str) -> Optional[int]:
                """切分文本：有句末标点则在最后一个标点后切，否则满 Lmin 时强切。"""
                if not buf:
                    return None
                last = -1
                for p in SENTENCE_PUNCT:
                    last = max(last, buf.rfind(p))
                if last >= 0:
                    return last + 1
                if len(buf) >= Lmin:
                    return len(buf)
                return None

            def _validate_wav_file(path: str) -> bool:
                try:
                    if not path or not os.path.exists(path):
                        return False
                    size = os.path.getsize(path)
                    if size < 800:
                        return False
                    import wave
                    with wave.open(path, "rb") as wf:
                        fr = wf.getframerate() or 0
                        nframes = wf.getnframes() or 0
                        if fr <= 0 or nframes <= 0:
                            return False
                        dur = nframes / fr
                        if dur < 0.15 or dur > 120:
                            return False
                    return True
                except Exception:
                    return False

            async def synthesize_and_store(idx: int, original_txt: str) -> None:
                nonlocal pending_tts
                try:
                    txt = _normalize_tts_text(original_txt)
                    if not txt:
                        completed_audio[idx] = ""
                        return
                    async with tts_sema:
                        path: Optional[str] = None
                        try:
                            path = await asyncio.wait_for(
                                voice_service.synthesize_xfyun(txt, voice=voice),
                                timeout=TTS_SENTENCE_TIMEOUT,
                            )
                            if path and _validate_wav_file(path):
                                with open(path, "rb") as f:
                                    b64 = base64.b64encode(f.read()).decode("utf-8")
                                completed_audio[idx] = b64
                                try:
                                    os.unlink(path)
                                except OSError:
                                    pass
                                return
                        except Exception as _tts_err:
                            logger.warning("TTS synthesis failed for chunk %d: %s", idx, _tts_err)
                        fallback_tts[idx] = original_txt.strip()
                        completed_audio[idx] = ""
                finally:
                    pending_tts = max(0, pending_tts - 1)
            
            def drain_audio():
                nonlocal next_audio_idx
                while next_audio_idx in completed_audio:
                    idx = next_audio_idx
                    b64 = completed_audio.pop(idx)
                    next_audio_idx += 1
                    if b64:
                        yield f"data: {json.dumps({'type': 'audio', 'content': b64}, ensure_ascii=False)}\n\n"
                    else:
                        if idx in fallback_tts:
                            text = fallback_tts.pop(idx)
                            if text:
                                yield f"data: {json.dumps({'type': 'tts', 'content': text}, ensure_ascii=False)}\n\n"
            
            yield f"data: {json.dumps({'type': 'attraction_id', 'content': primary_attraction_id}, ensure_ascii=False)}\n\n"
            chunk_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
            loop = asyncio.get_running_loop()
            stream_sentinel = object()
            
            def put_stream_in_queue():
                try:
                    for c in stream:
                        def _put():
                            try:
                                chunk_queue.put_nowait(c)
                            except asyncio.QueueFull:
                                # 队列满时丢弃最旧的一个，再写入当前chunk
                                try:
                                    chunk_queue.get_nowait()
                                except Exception:
                                    pass
                                try:
                                    chunk_queue.put_nowait(c)
                                except Exception:
                                    pass

                        loop.call_soon_threadsafe(_put)
                finally:
                    def _put_end():
                        try:
                            chunk_queue.put_nowait(stream_sentinel)
                        except Exception:
                            pass
                    loop.call_soon_threadsafe(_put_end)
            
            stream_future = loop.run_in_executor(None, put_stream_in_queue)
            DRAIN_INTERVAL = 0.05

            while True:
                try:
                    chunk = await asyncio.wait_for(chunk_queue.get(), timeout=DRAIN_INTERVAL)
                except asyncio.TimeoutError:
                    for ev in drain_audio():
                        yield ev
                    continue
                if chunk is stream_sentinel:
                    break
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'content') and delta.content:
                        raw_content = delta.content
                        logger.debug("RAW_CHUNK: %r", raw_content)
                        content = _clean_special_symbols(raw_content)
                        if raw_content != content:
                            logger.debug("CLEANED: %r -> %r", raw_content, content)
                        if not content:
                            continue
                        if content == prev_content:
                            logger.debug("DEDUP_SKIP: %r", content)
                            continue
                        prev_content = content
                        full_answer += content
                        accumulated_text += content
                        
                        tts_chunk = None
                        cut = _compute_cut(accumulated_text)
                        if cut is not None and cut > 0:
                            tts_chunk = accumulated_text[:cut]
                            accumulated_text = accumulated_text[cut:]
                        
                        if tts_chunk:
                            if backend_tts_enabled:
                                idx = tts_chunk_index[0]
                                tts_chunk_index[0] += 1
                                if pending_tts >= TTS_MAX_PENDING:
                                    fallback_tts[idx] = tts_chunk.strip()
                                    completed_audio[idx] = ""
                                else:
                                    pending_tts += 1
                                    asyncio.create_task(synthesize_and_store(idx, tts_chunk))
                            else:
                                yield f"data: {json.dumps({'type': 'tts', 'content': tts_chunk}, ensure_ascii=False)}\n\n"
                        
                        yield f"data: {json.dumps({'type': 'text', 'content': content}, ensure_ascii=False)}\n\n"
                
                for ev in drain_audio():
                    yield ev
            
            if accumulated_text.strip():
                if backend_tts_enabled:
                    idx = tts_chunk_index[0]
                    tts_chunk_index[0] += 1
                    if pending_tts >= TTS_MAX_PENDING:
                        fallback_tts[idx] = accumulated_text.strip()
                        completed_audio[idx] = ""
                    else:
                        pending_tts += 1
                        asyncio.create_task(synthesize_and_store(idx, accumulated_text.strip()))
                else:
                    yield f"data: {json.dumps({'type': 'tts', 'content': accumulated_text.strip()}, ensure_ascii=False)}\n\n"
            
            async def _write_stream_rag_log() -> None:
                try:
                    rag_debug: Optional[Dict[str, Any]] = None
                    if request.use_rag:
                        rag_debug = {
                            "query": (rag_results or {}).get("query") or request.query,
                            "vector_results": ((rag_results or {}).get("vector_results") or [])[:5],
                            "graph_results": ((rag_results or {}).get("graph_results") or [])[:5],
                            "subgraph": (rag_results or {}).get("subgraph"),
                            "enhanced_context": context or "",
                            "entities": (rag_results or {}).get("entities", []),
                            "errors": (rag_results or {}).get("errors", {}),
                            "intent": (rag_results or {}).get("intent"),
                            "strategy": (rag_results or {}).get("strategy"),
                            "final_sent_to_llm": user_prompt,
                        }
                    else:
                        rag_debug = {
                            "query": request.query,
                            "vector_results": [],
                            "graph_results": [],
                            "subgraph": None,
                            "enhanced_context": "",
                            "entities": [],
                            "skip_rag_reason": "未使用 RAG",
                            "final_sent_to_llm": user_prompt,
                        }

                    def _io_task():
                        try:
                            log_root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
                            os.makedirs(log_root, exist_ok=True)
                            log_path = os.path.join(log_root, "rag_context.log")
                            entry = {
                                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                                "query": request.query,
                                "character_prompt": character_prompt,
                                "use_rag": request.use_rag,
                                "rag_debug": rag_debug,
                                "final_answer_preview": (full_answer or "")[:2000],
                            }
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
                            logger.warning(f"Failed to write RAG context log (stream): {e}")

                    await asyncio.get_running_loop().run_in_executor(None, _io_task)
                except Exception as e:
                    logger.warning(f"Failed to schedule RAG context log (stream) write: {e}")

            try:
                asyncio.create_task(_write_stream_rag_log())
            except RuntimeError:
                try:
                    log_root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
                    os.makedirs(log_root, exist_ok=True)
                    log_path = os.path.join(log_root, "rag_context.log")
                    entry = {
                        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                        "query": request.query,
                        "character_prompt": character_prompt,
                        "use_rag": request.use_rag,
                        "rag_debug": None,
                        "final_answer_preview": (full_answer or "")[:2000],
                    }
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                except Exception as e:
                    logger.warning(f"Fallback write RAG context log (stream) failed: {e}")
            
            session_service.add_message(session_id, "user", request.query)
            session_service.add_message(session_id, "assistant", full_answer)

            await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: _save_interaction(
                    session_id,
                    request.character_id,
                    request.query,
                    full_answer,
                    primary_attraction_id,
                    request.scenic_name,
                    "voice_query",
                ),
            )
            _interaction_saved = True

            wait_start = time.monotonic()
            while next_audio_idx < tts_chunk_index[0] or completed_audio:
                if time.monotonic() - wait_start > 60:
                    logger.debug("流式 TTS 等待超时")
                    break
                await asyncio.sleep(DRAIN_INTERVAL)
                for ev in drain_audio():
                    yield ev
            
            yield f"data: {json.dumps({'type': 'done', 'content': full_answer}, ensure_ascii=False)}\n\n"
            
        except Exception as e:
            if stream_future is not None:
                stream_future.cancel()
            logger.error(f"Stream generation failed: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            # 客户端提前断连（导航切页）时，生成器会被取消，此处确保记录仍被保存
            if not _interaction_saved and full_answer.strip():
                try:
                    session_service.add_message(session_id, "user", request.query)
                    session_service.add_message(session_id, "assistant", full_answer)
                    _save_interaction(
                        session_id,
                        request.character_id,
                        request.query,
                        full_answer,
                        primary_attraction_id,
                        request.scenic_name,
                        "voice_query",
                    )
                except Exception as fe:
                    logger.error("Failed to save interaction in finally: %s", fe)

    return StreamingResponse(generate_stream(), media_type="text/event-stream")

