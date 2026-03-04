"""GraphRAG 检索 API"""
import base64
import logging
import asyncio
import json
import os
import time
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
    scenic_name: Optional[str] = None  # 指代消解用

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


def _get_attraction_id_name_list() -> List[Tuple[int, str]]:
    global _attraction_id_name_cache, _attraction_cache_time
    now = time.time()
    if _attraction_id_name_cache is not None and (now - _attraction_cache_time) < _ATTRACTION_CACHE_TTL:
        return _attraction_id_name_cache
    from app.core.database import SessionLocal
    from app.models.attraction import Attraction as AttractionModel
    db_local = SessionLocal()
    try:
        rows = (
            db_local.query(AttractionModel.id, AttractionModel.name)
            .filter(AttractionModel.name.isnot(None), AttractionModel.name != "")
            .limit(200)
            .all()
        )
        out = [(row[0], row[1] if len(row) > 1 else "") for row in rows]
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
) -> None:
    try:
        from app.core.database import SessionLocal
        from app.models.attraction import Attraction as AttractionModel
        db_local = SessionLocal()
        try:
            aid = primary_attraction_id
            if aid is None and query_text and query_text.strip():
                q = query_text.strip()
                for rid, name in _get_attraction_id_name_list():
                    if name and name in q:
                        aid = rid
                        break
            interaction = Interaction(
                session_id=session_id,
                character_id=character_id,
                query_text=query_text,
                response_text=response_text,
                interaction_type="voice_query",
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
        session_id = _resolve_session_id(request)
        (character_prompt, voice), conversation_history = await asyncio.gather(
            _load_character_prompt_and_voice(request.character_id),
            asyncio.to_thread(session_service.get_conversation_history, session_id),
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
        
        try:
            if not rag_service.llm_client:
                yield f"data: {json.dumps({'type': 'error', 'content': 'AI服务未配置'}, ensure_ascii=False)}\n\n"
                return
            
            stream = rag_service.llm_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
                stream=True
            )
            
            full_answer = ""
            accumulated_text = ""
            completed_audio: Dict[int, str] = {}
            fallback_tts: Dict[int, str] = {}  # TTS 失败时回退为文本由前端合成
            next_audio_idx = 0
            tts_chunk_index = [0]
            MIN_TTS_CHARS = 12
            TTS_SENTENCE_TIMEOUT = 25  # 单句 TTS 超时(秒)
            
            async def synthesize_and_store(idx: int, original_txt: str) -> None:
                txt = _normalize_tts_text(original_txt)
                if not txt:
                    completed_audio[idx] = ""
                    return
                path = None
                try:
                    try:
                        path = await asyncio.wait_for(
                            voice_service.synthesize_xfyun(txt, voice=voice),
                            timeout=TTS_SENTENCE_TIMEOUT,
                        )
                    except asyncio.TimeoutError:
                        logger.debug("科大讯飞 TTS 单句超时(%ds)", TTS_SENTENCE_TIMEOUT)
                    except Exception as e:
                        logger.debug("科大讯飞 TTS 失败: %s", e)
                    if path and os.path.exists(path):
                        with open(path, "rb") as f:
                            b64 = base64.b64encode(f.read()).decode("utf-8")
                        completed_audio[idx] = b64
                        try:
                            os.unlink(path)
                        except OSError:
                            pass
                    else:
                        fallback_tts[idx] = original_txt.strip()
                        completed_audio[idx] = ""
                except Exception as e:
                    logger.debug("流式 TTS 合成失败: %s", e)
                    fallback_tts[idx] = original_txt.strip()
                    completed_audio[idx] = ""
            
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
            
            yield f"data: {json.dumps({'type': 'session_id', 'content': session_id}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'attraction_id', 'content': primary_attraction_id}, ensure_ascii=False)}\n\n"
            chunk_queue: asyncio.Queue = asyncio.Queue()
            loop = asyncio.get_event_loop()
            stream_sentinel = object()
            
            def put_stream_in_queue():
                try:
                    for c in stream:
                        loop.call_soon_threadsafe(chunk_queue.put_nowait, c)
                finally:
                    loop.call_soon_threadsafe(chunk_queue.put_nowait, stream_sentinel)
            
            loop.run_in_executor(None, put_stream_in_queue)
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
                        content = delta.content
                        content = _clean_special_symbols(content)
                        if not content:
                            continue
                        full_answer += content
                        accumulated_text += content
                        
                        tts_chunk = None
                        if any(punct in accumulated_text for punct in ['。', '！', '？', '.', '!', '?']):
                            last_punct_idx = max(
                                accumulated_text.rfind('。'),
                                accumulated_text.rfind('！'),
                                accumulated_text.rfind('？'),
                                accumulated_text.rfind('.'),
                                accumulated_text.rfind('!'),
                                accumulated_text.rfind('?')
                            )
                            if last_punct_idx >= 0:
                                tts_chunk = accumulated_text[:last_punct_idx + 1]
                                accumulated_text = accumulated_text[last_punct_idx + 1:]
                        elif len(accumulated_text) >= MIN_TTS_CHARS:
                            tts_chunk = accumulated_text
                            accumulated_text = ""
                        
                        if tts_chunk:
                            if backend_tts_enabled:
                                idx = tts_chunk_index[0]
                                tts_chunk_index[0] += 1
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
                                if len(lines) > 5:
                                    with open(log_path, "w", encoding="utf-8") as f:
                                        f.writelines(lines[-5:])
                            except Exception:
                                pass
                        except Exception as e:
                            logger.warning(f"Failed to write RAG context log (stream): {e}")

                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, _io_task)
                except Exception as e:
                    logger.warning(f"Failed to schedule RAG context log (stream) write: {e}")

            try:
                asyncio.create_task(_write_stream_rag_log())
            except RuntimeError:
                # 若没有事件循环可用，则回退为同步写入，保证不影响主逻辑
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

            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: _save_interaction(
                    session_id,
                    request.character_id,
                    request.query,
                    full_answer,
                    primary_attraction_id,
                ),
            )
            
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
            logger.error(f"Stream generation failed: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(generate_stream(), media_type="text/event-stream")

