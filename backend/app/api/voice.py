"""
语音相关 API
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from typing import Optional
import tempfile
import os
from app.services.voice_service import voice_service

router = APIRouter()

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

@router.post("/synthesize")
async def synthesize_speech(
    text: str,
    method: str = "edge"
):
    """语音合成"""
    try:
        if method == "azure":
            audio_path = await voice_service.synthesize_azure(text)
        elif method == "edge":
            audio_path = await voice_service.synthesize_edge(text)
        else:
            raise HTTPException(status_code=400, detail="Unsupported method")
        
        return FileResponse(
            audio_path,
            media_type="audio/wav" if method == "azure" else "audio/mpeg",
            filename="speech.wav" if method == "azure" else "speech.mp3"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

