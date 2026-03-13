"""语音 API"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, Response
from starlette.background import BackgroundTask
from pydantic import BaseModel
from typing import Optional, List
import tempfile
import os
import re
import logging
import io
import wave
from app.services.voice_service import voice_service
from app.core.prisma_client import get_prisma
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

XFYUN_VOICE_OPTIONS = [
    {"value": "x4_xiaoyan", "label": "讯飞小燕（普通话）", "engine": "xfyun"},
    {"value": "x4_yezi", "label": "讯飞小露（普通话）", "engine": "xfyun"},
    {"value": "aisjiuxu", "label": "讯飞许久（普通话）", "engine": "xfyun"},
    {"value": "aisjinger", "label": "讯飞小婧（普通话）", "engine": "xfyun"},
    {"value": "aisbabyxu", "label": "讯飞许小宝（普通话）", "engine": "xfyun"},
]
XFYUN_VOICE_VALUES = {v["value"] for v in XFYUN_VOICE_OPTIONS}

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
_EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U0001F1E6-\U0001F1FF]+",
    flags=re.UNICODE,
)
_PUNCTUATION_RE = re.compile(r"[^\u4e00-\u9fff0-9\s]")

def _remove_invalid_unicode(text: str) -> str:
    try:
        text.encode('utf-8')
        return text
    except UnicodeEncodeError:
        result = []
        for char in text:
            try:
                char.encode('utf-8')
                result.append(char)
            except UnicodeEncodeError:
                continue
        return ''.join(result)

def _normalize_tts_text(text: str) -> str:
    text = (text or "").strip()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS_RE.sub("", text)
    text = _EMOJI_RE.sub("", text)
    text = _remove_invalid_unicode(text)
    text = _PUNCTUATION_RE.sub("", text)
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    if len(text) > 800:
        text = text[:800]
    return text


def _minimal_silent_wav_bytes() -> bytes:
    """无有效文本时返回静音 WAV，避免 400 断前端队列"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 800)
    return buf.getvalue()

@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    method: str = "whisper"
):
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            max_mb = int(getattr(settings, "VOICE_MAX_AUDIO_SIZE_MB", 15) or 15)
            max_bytes = max_mb * 1024 * 1024
            total = 0
            chunk_size = 1024 * 1024
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=400, detail=f"音频大小不能超过 {max_mb}MB")
                tmp_file.write(chunk)
            tmp_path = tmp_file.name
        
        if not tmp_path or not os.path.exists(tmp_path):
            raise HTTPException(status_code=500, detail="临时文件创建失败")
        
        file_size = os.path.getsize(tmp_path)
        logger.info(f"语音识别请求: method={method}, file_size={file_size} bytes")
        
        if method == "whisper":
            text = await voice_service.transcribe_whisper(tmp_path)
        elif method == "vosk":
            text = await voice_service.transcribe_vosk(tmp_path)
        else:
            raise HTTPException(status_code=400, detail="Unsupported method")
        
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        
        logger.info(f"语音识别成功: method={method}, text_length={len(text)}")
        return {"text": text, "method": method}
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"语音识别失败: method={method}, error={error_msg}", exc_info=True)
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"语音识别失败: {error_msg}")

class SynthesizeRequest(BaseModel):
    text: str
    voice: Optional[str] = None
    character_id: Optional[int] = None


class VoiceOption(BaseModel):
    value: str
    label: str
    engine: str = "xfyun"


@router.get("/voices", response_model=List[VoiceOption])
async def list_voices():
    return [VoiceOption(**v) for v in XFYUN_VOICE_OPTIONS]

@router.post("/synthesize")
async def synthesize_speech(
    req: SynthesizeRequest
):
    try:
        text = _normalize_tts_text(req.text)
        if not text:
            logger.debug("TTS 请求文本规范化后为空，返回静音 WAV")
            return Response(
                content=_minimal_silent_wav_bytes(),
                media_type="audio/wav",
                headers={"Content-Disposition": "inline; filename=speech.wav"},
            )
        voice = req.voice
        voice_from_request = bool(req.voice)
        
        if not voice and req.character_id:
            try:
                prisma = await get_prisma()
                character = await prisma.character.find_unique(where={"id": req.character_id})
                if character and character.voice:
                    voice = character.voice
                    voice_from_request = False
                    logger.info(f"使用角色 {req.character_id} 配置的语音: {voice}")
            except Exception as e:
                logger.warning(f"获取角色语音配置失败: {e}")
        if voice and voice not in XFYUN_VOICE_VALUES:
            if voice_from_request:
                raise HTTPException(
                    status_code=400,
                    detail=f"不支持的语音音色：{voice}（请从 /api/v1/voice/voices 获取可用列表）",
                )
            logger.warning(f"角色配置的语音不受支持，已忽略并回退到默认音色：{voice}")
            voice = None
        audio_path = None
        last_error = None

        try:
            audio_path = await voice_service.synthesize_xfyun(text, voice=voice)
        except Exception as e:
            last_error = e
            logger.error(f"科大讯飞 TTS 合成失败: {e}")

        if audio_path is None:
            raise HTTPException(status_code=400, detail=f"TTS 合成失败：{str(last_error) if last_error else 'unknown error'}")
        
        if not os.path.exists(audio_path):
            raise HTTPException(status_code=500, detail="音频文件生成失败")
        ext = os.path.splitext(audio_path)[1].lower()
        if ext == ".wav":
            media_type = "audio/wav"
            filename = "speech.wav"
        else:
            media_type = "audio/mpeg"
            filename = "speech.mp3"

        def _cleanup() -> None:
            try:
                if audio_path and os.path.exists(audio_path):
                    os.unlink(audio_path)
            except Exception:
                pass

        return FileResponse(
            audio_path,
            media_type=media_type,
            filename=filename,
            background=BackgroundTask(_cleanup),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS synthesize failed: {e}")
        error_detail = str(e)
        if "XFYUN_APPID" in error_detail or "XFYUN_API_KEY" in error_detail or "XFYUN_API_SECRET" in error_detail:
            error_detail = "科大讯飞 TTS 未配置。请设置 XFYUN_APPID / XFYUN_API_KEY / XFYUN_API_SECRET。"
        raise HTTPException(status_code=400, detail=f"TTS 合成失败：{error_detail}")

@router.post("/synthesize-stream")
async def synthesize_speech_stream(
    req: SynthesizeRequest
):
    try:
        text = _normalize_tts_text(req.text)
        if not text:
            logger.debug("TTS 流式请求文本规范化后为空，返回静音 WAV")
            return Response(
                content=_minimal_silent_wav_bytes(),
                media_type="audio/wav",
                headers={"Content-Disposition": "inline; filename=speech.wav"},
            )
        
        voice = req.voice
        voice_from_request = bool(req.voice)
        
        if not voice and req.character_id:
            try:
                prisma = await get_prisma()
                character = await prisma.character.find_unique(where={"id": req.character_id})
                if character and character.voice:
                    voice = character.voice
                    voice_from_request = False
            except Exception as e:
                logger.warning(f"获取角色语音配置失败: {e}")
        
        if voice and voice not in XFYUN_VOICE_VALUES:
            if voice_from_request:
                raise HTTPException(
                    status_code=400,
                    detail=f"不支持的语音音色：{voice}",
                )
            voice = None
        
        audio_path = None
        last_error = None

        try:
            audio_path = await voice_service.synthesize_xfyun(text, voice=voice)
        except Exception as e:
            last_error = e
            logger.debug("科大讯飞流式 TTS 失败: %s", e)

        if audio_path is None:
            raise HTTPException(status_code=400, detail=f"流式 TTS 合成失败：{str(last_error) if last_error else 'unknown error'}")
        
        if not os.path.exists(audio_path):
            raise HTTPException(status_code=500, detail="音频文件生成失败")
        
        ext = os.path.splitext(audio_path)[1].lower()
        if ext == ".wav":
            media_type = "audio/wav"
            filename = "speech.wav"
        else:
            media_type = "audio/mpeg"
            filename = "speech.mp3"

        def _cleanup() -> None:
            try:
                if audio_path and os.path.exists(audio_path):
                    os.unlink(audio_path)
            except Exception:
                pass

        return FileResponse(
            audio_path,
            media_type=media_type,
            filename=filename,
            background=BackgroundTask(_cleanup),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.debug("流式 TTS 失败: %s", e)
        raise HTTPException(status_code=400, detail=f"流式 TTS 合成失败：{str(e)}")

