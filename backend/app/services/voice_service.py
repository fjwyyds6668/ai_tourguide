"""
语音识别和合成服务
"""
import os
import tempfile
import re
from typing import Optional
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

class VoiceService:
    """语音处理服务，支持 Whisper/Vosk 识别和 Edge TTS/本地 TTS（Bert-VITS2）合成"""
    
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
            from vosk import SetLogLevel
            SetLogLevel(-1)
            logger.info("Vosk model initialization skipped (model not found)")
        except Exception as e:
            logger.warning(f"Failed to load Vosk: {e}")
    
    async def transcribe_whisper(self, audio_file_path: str) -> str:
        """使用 Whisper 进行语音识别"""
        if not self.whisper_model:
            raise ValueError("Whisper model not loaded")

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
    
    async def synthesize_edge(self, text: str, output_path: Optional[str] = None, voice: Optional[str] = None) -> str:
        """使用 Edge TTS 进行语音合成（带重试机制）
        
        Args:
            text: 要合成的文本
            output_path: 输出文件路径（可选）
            voice: 语音名称（可选，默认使用 zh-CN-XiaoxiaoNeural）
        """
        import edge_tts
        import asyncio
        
        if not output_path:
            output_path = tempfile.mktemp(suffix=".mp3")
        
        if not voice:
            voice = "zh-CN-XiaoxiaoNeural"
        
        try:
            text = text.encode('utf-8', errors='ignore').decode('utf-8')
        except Exception as e:
            logger.warning(f"文本清理失败: {e}")
            text = ''.join(char for char in text if ord(char) < 0x110000 and not (0xD800 <= ord(char) <= 0xDFFF))
        
        text = re.sub(r"[^\u4e00-\u9fff0-9\s]", "", text)
        text = re.sub(r"\s+", " ", text)
        text = text.strip()
        
        max_retries = 5
        last_error = None
        
        for attempt in range(max_retries):
            try:
                communicate = edge_tts.Communicate(text, voice)
                await asyncio.wait_for(communicate.save(output_path), timeout=30.0)
                
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    logger.info(f"Edge TTS 合成成功 (尝试 {attempt + 1}/{max_retries})")
                    return output_path
                else:
                    raise Exception("生成的音频文件为空")
                    
            except asyncio.TimeoutError:
                last_error = Exception("Edge TTS 请求超时")
                error_msg = "请求超时 (timeout)"
                logger.warning(f"Edge TTS 尝试 {attempt + 1}/{max_retries} 超时")
            except Exception as e:
                last_error = e
                error_msg = str(e)
                logger.warning(f"Edge TTS 尝试 {attempt + 1}/{max_retries} 失败: {e}")
                
                if "surrogates not allowed" in error_msg or "codec can't encode" in error_msg:
                    if attempt < max_retries - 1:
                        logger.info("检测到编码错误，清理文本后重试...")
                        text = ''.join(
                            char for char in text 
                            if ord(char) < 0x110000 and not (0xD800 <= ord(char) <= 0xDFFF)
                        )
                        text = re.sub(r'[\U0001F300-\U0001F9FF\U0001FA00-\U0001FAFF]', '', text)
                        text = re.sub(r'[\U00002700-\U000027BF]', '', text)
                        text = re.sub(r"[^\u4e00-\u9fff0-9\s]", "", text)
                        text = re.sub(r"\s+", " ", text)
                        text = text.strip()
                        if not text.strip():
                            raise Exception("文本清理后为空，无法合成")
                        continue
            
            is_connection_error = (
                "Cannot connect" in error_msg or 
                "远程主机强迫关闭" in error_msg or
                "Connection" in error_msg or
                "timeout" in error_msg.lower() or
                "timed out" in error_msg.lower()
            )
            
            if attempt < max_retries - 1:
                if is_connection_error:
                    wait_time = 2.0 * (2 ** attempt)
                    logger.info(f"检测到连接错误，等待 {wait_time:.1f} 秒后重试...")
                else:
                    wait_time = 0.5 * (2 ** attempt)
                
                await asyncio.sleep(wait_time)
            else:
                if "403" in error_msg or "Invalid response status" in error_msg:
                    raise Exception(
                        "Edge TTS 服务暂时不可用（403 错误）。"
                        "这可能是因为网络问题或 API 访问限制。"
                        "请稍后重试。"
                    )
                elif is_connection_error:
                    raise Exception(
                        f"Edge TTS 连接失败（已重试 {max_retries} 次）。"
                        "请检查网络连接或稍后重试。"
                        f"错误详情: {error_msg}"
                    )
                else:
                    raise Exception(f"Edge TTS 合成失败: {error_msg}")
        
        raise Exception(f"Edge TTS 合成失败: {last_error}")

    async def synthesize_local_bertvits2(
        self,
        text: str,
        output_path: Optional[str] = None,
        voice: Optional[str] = None,
    ) -> str:
        """
        离线本地 TTS（Bert-VITS2）- 高质量语音合成。

        voice: 说话人名称（如果为 None，使用配置中的默认说话人）
        """
        import asyncio
        from app.services.bertvits2_service import bertvits2_service

        if not output_path:
            output_path = tempfile.mktemp(suffix=".wav")

        if not bertvits2_service._initialized:
            config_path = settings.BERTVITS2_CONFIG_PATH
            model_path = settings.BERTVITS2_MODEL_PATH
            device = settings.BERTVITS2_DEVICE
            
            if not config_path or not model_path:
                raise Exception("Bert-VITS2 配置路径或模型路径未设置")
            
            # 将相对路径转换为绝对路径（相对于项目根目录）
            if not os.path.isabs(config_path):
                # backend/app/services/voice_service.py -> backend/app/services -> backend/app -> backend -> 项目根目录
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                config_path = os.path.join(project_root, config_path)
            if not os.path.isabs(model_path):
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                model_path = os.path.join(project_root, model_path)
            
            if not os.path.exists(config_path):
                raise Exception(f"Bert-VITS2 配置文件不存在: {config_path}")
            if not os.path.exists(model_path):
                raise Exception(f"Bert-VITS2 模型文件不存在: {model_path}")
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                bertvits2_service.initialize,
                config_path,
                model_path,
                device
            )

        speaker = voice or settings.BERTVITS2_DEFAULT_SPEAKER
        language = settings.BERTVITS2_LANGUAGE

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                bertvits2_service.synthesize,
                text,
                speaker,
                language,
                settings.BERTVITS2_SDP_RATIO,
                settings.BERTVITS2_NOISE_SCALE,
                settings.BERTVITS2_NOISE_SCALE_W,
                settings.BERTVITS2_LENGTH_SCALE,
                output_path
            )
        except Exception as e:
            logger.error(f"Bert-VITS2 合成失败: {e}")
            raise Exception(f"Bert-VITS2 TTS 合成失败: {e}")

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise Exception("Bert-VITS2 生成的音频文件为空")

        return output_path

# 全局语音服务实例
voice_service = VoiceService()

