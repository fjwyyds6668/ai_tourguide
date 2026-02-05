"""GraphRAG 检索 API"""
import logging
import asyncio
import json
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, AsyncGenerator
from app.services.rag_service import rag_service, _clean_special_symbols
from app.services.session_service import session_service
from app.core.prisma_client import get_prisma
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

class GenerateResponse(BaseModel):
    answer: str
    query: str
    context: str = ""
    session_id: str

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
        session_id = request.session_id
        if not session_id:
            session_id = session_service.create_session(request.character_id)
        else:
            session = session_service.get_session(session_id)
            if not session:
                session_id = session_service.create_session(request.character_id)
        # 并行加载角色提示词和对话历史
        async def load_character_prompt():
            if request.character_id:
                try:
                    prisma = await get_prisma()
                    character = await prisma.character.find_unique(where={"id": request.character_id})
                    if character and character.prompt:
                        return character.prompt
                except Exception as e:
                    logger.error(f"Failed to load character prompt: {e}")
            return None
        
        def load_conversation_history():
            return session_service.get_conversation_history(session_id)
        
        # 并行加载角色提示词和对话历史
        character_prompt, conversation_history = await asyncio.gather(
            load_character_prompt(),
            asyncio.to_thread(load_conversation_history)
        )
        
        result = await rag_service.generate_answer(
            query=request.query,
            context=None,
            use_rag=request.use_rag,
            conversation_history=conversation_history,
            character_prompt=character_prompt
        )
        answer = result["answer"]
        context = result.get("context", "")
        primary_attraction_id = result.get("primary_attraction_id")
        
        # 立即更新会话历史（同步操作，很快）
        session_service.add_message(session_id, "user", request.query)
        session_service.add_message(session_id, "assistant", answer)
        
        # 数据库保存使用后台任务，不阻塞响应
        def save_interaction():
            try:
                from app.core.database import SessionLocal
                from app.models.attraction import Attraction as AttractionModel
                db_local = SessionLocal()
                try:
                    aid = primary_attraction_id
                    # 若 RAG 未返回景点 ID，根据问题文本尝试按景点名称匹配（便于服务次数统计）
                    if aid is None and request.query and request.query.strip():
                        q = (request.query or "").strip()
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
                        character_id=request.character_id,
                        query_text=request.query,
                        response_text=answer,
                        interaction_type="voice_query",
                        attraction_id=aid,
                    )
                    db_local.add(interaction)
                    db_local.commit()
                finally:
                    db_local.close()
            except Exception as e:
                logger.error(f"Failed to save interaction: {e}")
        
        background_tasks.add_task(save_interaction)
        
        return GenerateResponse(
            answer=answer,
            query=request.query,
            context=context,
            session_id=session_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate-stream")
async def generate_answer_stream(request: GenerateRequest, background_tasks: BackgroundTasks):
    """流式生成回答（SSE），文本与 TTS 同步输出"""
    async def generate_stream() -> AsyncGenerator[str, None]:
        session_id = request.session_id
        if not session_id:
            session_id = session_service.create_session(request.character_id)
        else:
            session = session_service.get_session(session_id)
            if not session:
                session_id = session_service.create_session(request.character_id)
        
        # 并行加载角色提示词和对话历史
        async def load_character_prompt():
            if request.character_id:
                try:
                    prisma = await get_prisma()
                    character = await prisma.character.find_unique(where={"id": request.character_id})
                    if character and character.prompt:
                        return character.prompt
                except Exception as e:
                    logger.error(f"Failed to load character prompt: {e}")
            return None
        
        def load_conversation_history():
            return session_service.get_conversation_history(session_id)
        
        character_prompt, conversation_history = await asyncio.gather(
            load_character_prompt(),
            asyncio.to_thread(load_conversation_history)
        )
        
        # 执行 RAG 检索（非流式，一次性获取上下文）
        rag_results = None
        primary_attraction_id = None
        context = ""
        if request.use_rag:
            try:
                rag_results = await rag_service.hybrid_search(request.query, top_k=5)
                primary_attraction_id = rag_results.get("primary_attraction_id")
                context = rag_results.get("enhanced_context", "") or ""
            except Exception as e:
                logger.error(f"RAG search failed: {e}")
        
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
            from app.core.config import settings
            stream = rag_service.llm_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
                stream=True
            )
            
            full_answer = ""
            accumulated_text = ""
            
            # 发送 session_id
            yield f"data: {json.dumps({'type': 'session_id', 'content': session_id}, ensure_ascii=False)}\n\n"
            
            # 发送 primary_attraction_id（用于后续保存交互）
            yield f"data: {json.dumps({'type': 'attraction_id', 'content': primary_attraction_id}, ensure_ascii=False)}\n\n"
            
            # 流式接收并转发文本
            for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'content') and delta.content:
                        content = delta.content
                        # 清理特殊符号
                        content = _clean_special_symbols(content)
                        if not content:
                            continue
                        full_answer += content
                        accumulated_text += content
                        
                        # 当累积文本达到一定长度（如遇到句号、问号、感叹号）时，发送一段用于 TTS
                        if any(punct in accumulated_text for punct in ['。', '！', '？', '.', '!', '?']):
                            # 找到最后一个标点
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
                                yield f"data: {json.dumps({'type': 'tts', 'content': tts_chunk}, ensure_ascii=False)}\n\n"
                        
                        # 发送文本增量
                        yield f"data: {json.dumps({'type': 'text', 'content': content}, ensure_ascii=False)}\n\n"
            
            # 发送剩余的累积文本（如果有）
            if accumulated_text.strip():
                yield f"data: {json.dumps({'type': 'tts', 'content': accumulated_text.strip()}, ensure_ascii=False)}\n\n"
            
            # 发送完成信号
            yield f"data: {json.dumps({'type': 'done', 'content': full_answer}, ensure_ascii=False)}\n\n"
            
            # 更新会话历史
            session_service.add_message(session_id, "user", request.query)
            session_service.add_message(session_id, "assistant", full_answer)
            
            # 后台保存交互记录
            def save_interaction():
                try:
                    from app.core.database import SessionLocal
                    from app.models.attraction import Attraction as AttractionModel
                    db_local = SessionLocal()
                    try:
                        aid = primary_attraction_id
                        if aid is None and request.query and request.query.strip():
                            q = (request.query or "").strip()
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
                            character_id=request.character_id,
                            query_text=request.query,
                            response_text=full_answer,
                            interaction_type="voice_query",
                            attraction_id=aid,
                        )
                        db_local.add(interaction)
                        db_local.commit()
                    finally:
                        db_local.close()
                except Exception as e:
                    logger.error(f"Failed to save interaction: {e}")
            
            background_tasks.add_task(save_interaction)
            
        except Exception as e:
            logger.error(f"Stream generation failed: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(generate_stream(), media_type="text/event-stream")

