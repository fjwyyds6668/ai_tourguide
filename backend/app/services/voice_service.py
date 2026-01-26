"""
语音识别和合成服务
"""
import os
import tempfile
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class VoiceService:
    """语音处理服务，支持 Whisper/Vosk 识别和 Azure/Edge TTS 合成"""
    
    def __init__(self):
        self.whisper_model = None
        self.vosk_model = None
        self._init_models()
    
    def _init_models(self):
        """初始化语音识别模型"""
        try:
            import whisper
            self.whisper_model = whisper.load_model("base")
            logger.info("Whisper model loaded")
        except Exception as e:
            logger.warning(f"Failed to load Whisper: {e}")
        
        try:
            from vosk import Model, SetLogLevel
            SetLogLevel(-1)
            # 需要下载 Vosk 模型
            # model_path = "path/to/vosk-model"
            # if os.path.exists(model_path):
            #     self.vosk_model = Model(model_path)
            logger.info("Vosk model initialization skipped (model not found)")
        except Exception as e:
            logger.warning(f"Failed to load Vosk: {e}")
    
    async def transcribe_whisper(self, audio_file_path: str) -> str:
        """使用 Whisper 进行语音识别"""
        if not self.whisper_model:
            raise ValueError("Whisper model not loaded")
        
        import whisper
        result = self.whisper_model.transcribe(audio_file_path, language="zh")
        return result["text"].strip()
    
    async def transcribe_vosk(self, audio_file_path: str) -> str:
        """使用 Vosk 进行语音识别"""
        if not self.vosk_model:
            raise ValueError("Vosk model not loaded")
        
        import json
        import wave
        from vosk import KaldiRecognizer
        
        wf = wave.open(audio_file_path, "rb")
        rec = KaldiRecognizer(self.vosk_model, wf.getframerate())
        rec.SetWords(True)
        
        text_parts = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                if 'text' in result:
                    text_parts.append(result['text'])
        
        final_result = json.loads(rec.FinalResult())
        if 'text' in final_result:
            text_parts.append(final_result['text'])
        
        return " ".join(text_parts)
    
    async def synthesize_azure(self, text: str, output_path: Optional[str] = None) -> str:
        """使用 Azure TTS 进行语音合成"""
        from app.core.config import settings
        import azure.cognitiveservices.speech as speechsdk
        
        speech_config = speechsdk.SpeechConfig(
            subscription=settings.AZURE_SPEECH_KEY,
            region=settings.AZURE_SPEECH_REGION
        )
        speech_config.speech_synthesis_voice_name = "zh-CN-XiaoxiaoNeural"
        
        if not output_path:
            output_path = tempfile.mktemp(suffix=".wav")
        
        audio_config = speechsdk.audio.AudioOutputConfig(filename=output_path)
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config,
            audio_config=audio_config
        )
        
        result = synthesizer.speak_text_async(text).get()
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            return output_path
        else:
            raise Exception(f"Azure TTS failed: {result.reason}")
    
    async def synthesize_edge(self, text: str, output_path: Optional[str] = None) -> str:
        """使用 Edge TTS 进行语音合成（带重试机制）"""
        import edge_tts
        import asyncio
        
        if not output_path:
            output_path = tempfile.mktemp(suffix=".mp3")
        
        voice = "zh-CN-XiaoxiaoNeural"
        
        # 重试机制：最多重试 3 次
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                communicate = edge_tts.Communicate(text, voice)
                await communicate.save(output_path)
                
                # 检查文件是否成功生成
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    return output_path
                else:
                    raise Exception("生成的音频文件为空")
                    
            except Exception as e:
                last_error = e
                logger.warning(f"Edge TTS 尝试 {attempt + 1}/{max_retries} 失败: {e}")
                
                if attempt < max_retries - 1:
                    # 等待后重试（指数退避）
                    await asyncio.sleep(0.5 * (2 ** attempt))
                else:
                    # 最后一次尝试失败，抛出更友好的错误
                    error_msg = str(e)
                    if "403" in error_msg or "Invalid response status" in error_msg:
                        raise Exception(
                            "Edge TTS 服务暂时不可用（403 错误）。"
                            "这可能是因为网络问题或 API 访问限制。"
                            "请稍后重试，或考虑使用 Azure TTS。"
                        )
                    else:
                        raise Exception(f"Edge TTS 合成失败: {error_msg}")
        
        # 理论上不会到达这里
        raise Exception(f"Edge TTS 合成失败: {last_error}")

# 全局语音服务实例
voice_service = VoiceService()

