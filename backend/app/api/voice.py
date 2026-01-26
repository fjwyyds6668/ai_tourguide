"""
语音相关 API
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import tempfile
import os
import re
import logging
from app.services.voice_service import voice_service

router = APIRouter()
logger = logging.getLogger(__name__)

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
# 粗略去掉常见 emoji 范围（避免 edge-tts 在少数字符上报错）
_EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U0001F1E6-\U0001F1FF]+",
    flags=re.UNICODE,
)

def _normalize_tts_text(text: str) -> str:
    text = (text or "").strip()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS_RE.sub("", text)
    text = _EMOJI_RE.sub("", text)
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
    method: str = "edge"

@router.post("/synthesize")
async def synthesize_speech(
    req: SynthesizeRequest
):
    """语音合成（支持自动降级）"""
    try:
        text = _normalize_tts_text(req.text)
        method = (req.method or "edge").lower()

        if not text:
            raise HTTPException(status_code=400, detail="要合成的文本为空")

        audio_path = None
        error = None
        
        # 尝试使用指定的方法
        try:
            if method == "azure":
                audio_path = await voice_service.synthesize_azure(text)
            elif method == "edge":
                audio_path = await voice_service.synthesize_edge(text)
            else:
                raise HTTPException(status_code=400, detail="Unsupported method")
        except Exception as e:
            error = e
            logger.warning(f"TTS method '{method}' failed: {e}")
            
            # 如果 Edge TTS 失败，尝试降级到 Azure（如果配置了）
            if method == "edge":
                try:
                    from app.core.config import settings
                    if settings.AZURE_SPEECH_KEY and settings.AZURE_SPEECH_REGION:
                        logger.info("Edge TTS 失败，尝试使用 Azure TTS 作为降级方案")
                        audio_path = await voice_service.synthesize_azure(text)
                        method = "azure"  # 更新方法以便返回正确的媒体类型
                    else:
                        raise error  # 如果没有 Azure 配置，抛出原始错误
                except Exception as azure_error:
                    logger.error(f"Azure TTS 降级也失败: {azure_error}")
                    raise error  # 抛出原始 Edge TTS 错误
        
        if not audio_path or not os.path.exists(audio_path):
            raise HTTPException(status_code=500, detail="音频文件生成失败")
        
        return FileResponse(
            audio_path,
            media_type="audio/wav" if method == "azure" else "audio/mpeg",
            filename="speech.wav" if method == "azure" else "speech.mp3"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS synthesize failed: {e}")
        # 提供更友好的错误信息
        error_detail = str(e)
        if "403" in error_detail or "Invalid response status" in error_detail:
            error_detail = "TTS 服务暂时不可用，请稍后重试或检查网络连接"
        raise HTTPException(status_code=400, detail=f"TTS 合成失败：{error_detail}")

