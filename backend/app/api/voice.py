"""
语音相关 API
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import tempfile
import os
import re
import logging
from app.services.voice_service import voice_service
from app.core.prisma_client import get_prisma
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
# 粗略去掉常见 emoji 范围（避免 edge-tts 在少数字符上报错）
_EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U0001F1E6-\U0001F1FF]+",
    flags=re.UNICODE,
)
# 匹配中文字符（包括中文标点）
_CHINESE_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
# 匹配数字
_DIGIT_RE = re.compile(r"[0-9]")
# 匹配所有标点符号和特殊字符（保留空格和换行）
_PUNCTUATION_RE = re.compile(r"[^\u4e00-\u9fff0-9\s]")

def _remove_invalid_unicode(text: str) -> str:
    """移除无效的 Unicode 代理对字符"""
    try:
        # 先尝试编码为 UTF-8，如果失败则过滤掉无效字符
        text.encode('utf-8')
        return text
    except UnicodeEncodeError:
        # 如果有编码错误，逐个字符检查并过滤
        result = []
        for char in text:
            try:
                char.encode('utf-8')
                result.append(char)
            except UnicodeEncodeError:
                # 跳过无效字符
                continue
        return ''.join(result)

def _normalize_tts_text(text: str) -> str:
    text = (text or "").strip()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS_RE.sub("", text)
    text = _EMOJI_RE.sub("", text)
    # 移除无效的 Unicode 代理对字符
    text = _remove_invalid_unicode(text)
    # 移除所有标点符号，只保留中文、数字和空格
    text = _PUNCTUATION_RE.sub("", text)
    # 将多个连续空格替换为单个空格
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    # 避免超长文本导致合成慢/失败/资源占用过大
    if len(text) > 800:
        text = text[:800]
    return text

@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    method: str = "whisper"
):
    """语音识别"""
    try:
        # 保存上传的音频文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name
        
        # 根据方法选择识别引擎
        if method == "whisper":
            text = await voice_service.transcribe_whisper(tmp_path)
        elif method == "vosk":
            text = await voice_service.transcribe_vosk(tmp_path)
        else:
            raise HTTPException(status_code=400, detail="Unsupported method")
        
        # 清理临时文件
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

@router.post("/synthesize")
async def synthesize_speech(
    req: SynthesizeRequest
):
    """语音合成（优先 Edge TTS，失败可降级到离线 Piper）"""
    try:
        text = _normalize_tts_text(req.text)

        if not text:
            raise HTTPException(status_code=400, detail="要合成的文本为空")

        # 确定使用的语音
        voice = req.voice
        
        # 如果提供了角色ID但没有提供语音，尝试从角色配置获取
        if not voice and req.character_id:
            try:
                prisma = await get_prisma()
                character = await prisma.character.find_unique(where={"id": req.character_id})
                if character and character.voice:
                    voice = character.voice
                    logger.info(f"使用角色 {req.character_id} 配置的语音: {voice}")
            except Exception as e:
                logger.warning(f"获取角色语音配置失败: {e}")

        # 优先 Edge TTS；如启用离线 TTS，则在 Edge 失败（403/网络）时降级到 Piper
        audio_path = None
        last_error = None

        if not settings.LOCAL_TTS_FORCE:
            try:
                audio_path = await voice_service.synthesize_edge(text, voice=voice)
            except Exception as e:
                last_error = e
                logger.error(f"Edge TTS 合成失败: {e}")

        if (audio_path is None) and settings.LOCAL_TTS_ENABLED:
            try:
                # 本地 TTS 使用 PaddleSpeech：
                # - voice 传入 settings.PADDLESPEECH_VOICES_JSON 的 key，可实现多音色
                audio_path = await voice_service.synthesize_local_paddlespeech(text, voice=voice)
                last_error = None
            except Exception as e:
                last_error = e
                logger.error(f"Local PaddleSpeech TTS 合成失败: {e}")

        if audio_path is None:
            raise HTTPException(status_code=400, detail=f"TTS 合成失败：{str(last_error) if last_error else 'unknown error'}")
        
        if not audio_path or not os.path.exists(audio_path):
            raise HTTPException(status_code=500, detail="音频文件生成失败")

        # 根据输出文件扩展名设置 media_type
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
        # 提供更友好的错误信息
        error_detail = str(e)
        if "403" in error_detail or "Invalid response status" in error_detail:
            error_detail = "Edge TTS 服务暂时不可用（403）。建议启用离线 Piper TTS 或检查网络/限制。"
        raise HTTPException(status_code=400, detail=f"TTS 合成失败：{error_detail}")

