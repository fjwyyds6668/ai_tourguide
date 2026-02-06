"""GraphRAG 检索 API"""
import base64
import logging
import asyncio
import json
import os
import time
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple
from app.services.rag_service import rag_service, _clean_special_symbols
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
    scenic_name: Optional[str] = None  # 用户选择的景区名称，用于指代消解（如「这个景区」）

class GenerateResponse(BaseModel):
    answer: str
    query: str
    context: str = ""
    session_id: str


def _resolve_session_id(request: GenerateRequest) -> str:
    """根据请求解析或创建 session_id，供 /generate 与 /generate-stream 共用。"""
    if request.session_id:
        session = session_service.get_session(request.session_id)
        if session:
            return request.session_id
    return session_service.create_session(request.character_id)


async def _load_character_prompt_and_voice(character_id: Optional[int]) -> Tuple[Optional[str], Optional[str]]:
    """一次查询角色，返回 (prompt, voice)，供 /generate 与 /generate-stream 共用，避免重复查库。"""
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


def _save_interaction(
    session_id: str,
    character_id: Optional[int],
    query_text: str,
    response_text: str,
    primary_attraction_id: Optional[int],
) -> None:
    """保存交互记录到数据库；未返回景点 ID 时按问题文本尝试匹配景点名。供 /generate 与 /generate-stream 共用。"""
    try:
        from app.core.database import SessionLocal
        from app.models.attraction import Attraction as AttractionModel
        db_local = SessionLocal()
        try:
            aid = primary_attraction_id
            if aid is None and query_text and query_text.strip():
                q = query_text.strip()
                rows = (
                    db_local.query(AttractionModel.id, AttractionModel.name)
                    .filter(AttractionModel.name.isnot(None), AttractionModel.name != "")
                    .limit(200)
                    .all()
                )
                for row in rows:
                    name = row[1] if len(row) > 1 else None
                    if name and name in q:
                        aid = row[0]
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
    """混合检索"""
    try:
        results = await rag_service.hybrid_search(request.query, top_k=request.top_k)
        return QueryResponse(**results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/vector-search")
async def vector_search(request: QueryRequest):
    """向量搜索"""
    try:
        results = await rag_service.vector_search(request.query, top_k=request.top_k)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/graph-search")
async def graph_search(entity_name: str, relation_type: str = None, limit: int = 10):
    """图搜索"""
    try:
        results = await rag_service.graph_search(entity_name, relation_type, limit)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate", response_model=GenerateResponse)
async def generate_answer(request: GenerateRequest, background_tasks: BackgroundTasks):
    """生成回答（RAG + 多轮对话）。"""
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
    """流式生成回答（SSE），文本与 TTS 同步输出"""
    async def generate_stream() -> AsyncGenerator[str, None]:
        session_id = _resolve_session_id(request)
        (character_prompt, voice), conversation_history = await asyncio.gather(
            _load_character_prompt_and_voice(request.character_id),
            asyncio.to_thread(session_service.get_conversation_history, session_id),
        )
        if not voice:
            voice = settings.XFYUN_VOICE
        
        # 执行 RAG 检索（非流式，一次性获取上下文）
        rag_results = None
        primary_attraction_id = None
        context = ""
        if request.use_rag:
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
        
        # 准备 LLM 消息
        base_system_prompt = """你是一个专业的景区AI导游助手。请根据提供的上下文信息，用友好、专业、准确的语言回答游客的问题。
回答要求：
1. 基于提供的上下文信息回答
2. 语言简洁明了，适合口语化表达
3. 如果信息不足，诚实说明
4. 不要编造信息
5. 不要透露任何内部标识符/编号/ID（例如 kb_***、text_id、session_id 等）；自我介绍时也不要输出任何"编号"
6. 输出内容必须为"干净的纯文本"：
   - 禁止使用任何表情符号、emoji、颜文字（如 🌟、✨、❤️、😊、1️⃣、2️⃣ 等）
   - 禁止使用 Markdown 格式符号（如 **粗体**、*斜体*、# 标题、- 列表符号等）
   - 禁止使用装饰性符号（如 ～、~、——、…、•、▪、▫ 等）
   - 只使用正常中文标点（，。！？：；）与必要的数字、单位
   - 如需列举，使用"第一"、"第二"或"1."、"2."等纯文本格式，不要用特殊符号"""
        
        if character_prompt:
            system_prompt = f"{base_system_prompt}\n\n角色设定：{character_prompt}"
        else:
            system_prompt = base_system_prompt

        # 是否在后端做 TTS（科大讯飞或本地 CosyVoice2），边生成边合成
        backend_tts_enabled = bool(settings.XFYUN_APPID and settings.XFYUN_API_KEY) or settings.LOCAL_TTS_ENABLED
        
        messages = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            messages.extend(conversation_history)
        
        user_prompt = f"""用户问题：{request.query}
上下文信息：
{context if context else "无额外上下文信息"}

请基于以上信息回答用户的问题。"""
        messages.append({"role": "user", "content": user_prompt})
        
        # 流式调用 LLM
        try:
            if not rag_service.llm_client:
                yield f"data: {json.dumps({'type': 'error', 'content': 'AI服务未配置'}, ensure_ascii=False)}\n\n"
                return
            
            # 使用流式 API
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
            fallback_tts: Dict[int, str] = {}  # 后端 TTS 失败时，按句回退为 tts 文本给前端合成
            next_audio_idx = 0
            tts_chunk_index = [0]
            MIN_TTS_CHARS = 12
            TTS_SENTENCE_TIMEOUT = 25  # 单句合成超时（秒），避免某句卡住拖死整段
            
            async def synthesize_and_store(idx: int, original_txt: str) -> None:
                txt = _normalize_tts_text(original_txt)
                if not txt:
                    completed_audio[idx] = ""
                    return
                path = None
                try:
                    if not settings.LOCAL_TTS_FORCE:
                        try:
                            path = await asyncio.wait_for(
                                voice_service.synthesize_xfyun(txt, voice=voice),
                                timeout=TTS_SENTENCE_TIMEOUT,
                            )
                        except asyncio.TimeoutError:
                            logger.debug("科大讯飞 TTS 单句超时(%ds)", TTS_SENTENCE_TIMEOUT)
                        except Exception as e:
                            logger.debug("科大讯飞 TTS 失败: %s", e)
                    if path is None and settings.LOCAL_TTS_ENABLED:
                        try:
                            path = await asyncio.wait_for(
                                voice_service.synthesize_local_cosyvoice2(txt, voice=voice),
                                timeout=TTS_SENTENCE_TIMEOUT,
                            )
                        except asyncio.TimeoutError:
                            logger.debug("CosyVoice2 TTS 单句超时")
                        except Exception as e:
                            logger.debug("CosyVoice2 TTS 失败: %s", e)
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
                        # 后端合成失败，按句回退：发 tts 文本让前端 POST 合成
                        if idx in fallback_tts:
                            text = fallback_tts.pop(idx)
                            if text:
                                yield f"data: {json.dumps({'type': 'tts', 'content': text}, ensure_ascii=False)}\n\n"
            
            # 发送 session_id
            yield f"data: {json.dumps({'type': 'session_id', 'content': session_id}, ensure_ascii=False)}\n\n"
            
            # 发送 primary_attraction_id（用于后续保存交互）
            yield f"data: {json.dumps({'type': 'attraction_id', 'content': primary_attraction_id}, ensure_ascii=False)}\n\n"
            
            # 用队列 + 后台消费 stream，主循环每 50ms 检查一次：有 chunk 就处理并 yield 文本，无 chunk 就 drain 已就绪的音频并 yield，实现「边出字边出声音」
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
                
                # 每处理完一个 chunk 或超时都 drain 已就绪的音频，实现边出字边播放
                for ev in drain_audio():
                    yield ev
            
            # 剩余累积文本
            if accumulated_text.strip():
                if backend_tts_enabled:
                    idx = tts_chunk_index[0]
                    tts_chunk_index[0] += 1
                    asyncio.create_task(synthesize_and_store(idx, accumulated_text.strip()))
                else:
                    yield f"data: {json.dumps({'type': 'tts', 'content': accumulated_text.strip()}, ensure_ascii=False)}\n\n"
            
            # 先写入 RAG 日志并保存交互，管理端可立即看到更新（不必等 TTS 全部播完）
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
                log_root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
                os.makedirs(log_root, exist_ok=True)
                log_path = os.path.join(log_root, "rag_context.log")
                entry = {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "query": request.query,
                    "character_prompt": character_prompt,
                    "use_rag": request.use_rag,
                    "rag_debug": rag_debug,
                    "final_answer_preview": (full_answer or "")[:400],
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
            
            # 等待所有 TTS 完成并持续 drain 音频（边等边 yield，用户能边听）
            wait_start = time.monotonic()
            while next_audio_idx < tts_chunk_index[0] or completed_audio:
                if time.monotonic() - wait_start > 60:
                    logger.debug("流式 TTS 等待超时")
                    break
                await asyncio.sleep(DRAIN_INTERVAL)
                for ev in drain_audio():
                    yield ev
            
            # 发送完成信号
            yield f"data: {json.dumps({'type': 'done', 'content': full_answer}, ensure_ascii=False)}\n\n"
            
        except Exception as e:
            logger.error(f"Stream generation failed: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(generate_stream(), media_type="text/event-stream")

