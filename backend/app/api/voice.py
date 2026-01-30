"""
语音相关 API
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, Response
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
    """移除无效的 Unicode 代理对字符"""
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
    """生成极短静音 WAV（约 0.1 秒），用于「规范化后无有效内容」时避免返回 400、保持前端队列不中断。"""
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
    """语音识别"""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name
        if method == "whisper":
            text = await voice_service.transcribe_whisper(tmp_path)
        elif method == "vosk":
            text = await voice_service.transcribe_vosk(tmp_path)
        else:
            raise HTTPException(status_code=400, detail="Unsupported method")
        os.unlink(tmp_path)
        
        return {"text": text, "method": method}
    except Exception as e:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise HTTPException(status_code=500, detail=str(e))

class SynthesizeRequest(BaseModel):
    text: str
    voice: Optional[str] = None  # 语音名称，如果提供则使用，否则从角色配置获取
    character_id: Optional[int] = None  # 角色ID，用于获取角色的语音配置


class VoiceOption(BaseModel):
    value: str
    label: str
    engine: str = "xfyun"


@router.get("/voices", response_model=List[VoiceOption])
async def list_voices():
    """获取可用语音列表（当前仅返回科大讯飞 vcn 列表）"""
    return [VoiceOption(**v) for v in XFYUN_VOICE_OPTIONS]

@router.post("/synthesize")
async def synthesize_speech(
    req: SynthesizeRequest
):
    """语音合成（优先科大讯飞 TTS，失败可降级到离线本地 TTS：CosyVoice2）"""
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
        
        # 如果提供了角色ID但没有提供语音，尝试从角色配置获取
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

        if not settings.LOCAL_TTS_FORCE:
            try:
                audio_path = await voice_service.synthesize_xfyun(text, voice=voice)
            except Exception as e:
                last_error = e
                logger.error(f"科大讯飞 TTS 合成失败: {e}")

        if (audio_path is None) and settings.LOCAL_TTS_ENABLED:
            try:
                audio_path = await voice_service.synthesize_local_cosyvoice2(text, voice=voice)
                last_error = None
                logger.info("使用 CosyVoice2 TTS（备用方案）合成成功")
            except Exception as e:
                last_error = e
                logger.error(f"CosyVoice2 TTS（备用方案）合成失败: {e}")

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

        return FileResponse(audio_path, media_type=media_type, filename=filename)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS synthesize failed: {e}")
        error_detail = str(e)
        if "XFYUN_APPID" in error_detail or "XFYUN_API_KEY" in error_detail or "XFYUN_API_SECRET" in error_detail:
            error_detail = "科大讯飞 TTS 未配置。请设置 XFYUN_APPID / XFYUN_API_KEY / XFYUN_API_SECRET，或启用离线本地 TTS（CosyVoice2）。"
        raise HTTPException(status_code=400, detail=f"TTS 合成失败：{error_detail}")

