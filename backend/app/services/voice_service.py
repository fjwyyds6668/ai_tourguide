"""
语音识别和合成服务
"""
import os
import tempfile
from typing import Optional
from pathlib import Path
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
        """使用 Edge TTS 进行语音合成"""
        import edge_tts
        import asyncio
        
        if not output_path:
            output_path = tempfile.mktemp(suffix=".mp3")
        
        voice = "zh-CN-XiaoxiaoNeural"
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        
        return output_path

# 全局语音服务实例
voice_service = VoiceService()

