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
    """语音处理服务，支持 Whisper/Vosk 识别和 Edge TTS/本地 TTS（PaddleSpeech）合成"""
    
    def __init__(self):
        self.whisper_model = None
        self.vosk_model = None
        # PaddleSpeech TTSExecutor 缓存（按 am+voc 组合缓存）
        self._paddlespeech_executors: dict[str, any] = {}
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

    async def synthesize_local_paddlespeech(
        self,
        text: str,
        output_path: Optional[str] = None,
        voice: Optional[str] = None,
    ) -> str:
        """
        离线本地 TTS（PaddleSpeech）- 优化版本，使用进程内调用和模型缓存。

        直接使用 Python API 调用 PaddleSpeech，避免子进程开销，并缓存 TTSExecutor 实例。
        voice: 使用 settings.paddlespeech_voices 的 key；找不到则回退到 settings.PADDLESPEECH_DEFAULT_VOICE
        """
        import asyncio
        import threading

        if not output_path:
            output_path = tempfile.mktemp(suffix=".wav")

        voices = settings.paddlespeech_voices
        voice_key = voice if (voice and voice in voices) else settings.PADDLESPEECH_DEFAULT_VOICE
        cfg = voices.get(voice_key, {})

        am = cfg.get("am", voice_key)
        voc = cfg.get("voc", "pwgan_csmsc")
        lang = cfg.get("lang", "zh")
        spk_id = cfg.get("spk_id", None)

        cache_key = f"{am}_{voc}_{lang}"
        if spk_id is not None:
            cache_key += f"_spk{spk_id}"

        executor_lock = threading.Lock()
        loop = asyncio.get_event_loop()
        
        with executor_lock:
            if cache_key not in self._paddlespeech_executors:
                try:
                    logger.info(f"初始化 PaddleSpeech TTSExecutor (am={am}, voc={voc})...")
                    logger.info("注意: 首次运行会下载模型（可能较慢，请耐心等待）...")
                    
                    executor = await loop.run_in_executor(
                        None,
                        self._init_paddlespeech_executor,
                        am, voc, lang
                    )
                    self._paddlespeech_executors[cache_key] = executor
                    logger.info(f"PaddleSpeech TTSExecutor 已缓存: {cache_key}")
                except Exception as e:
                    logger.error(f"初始化 PaddleSpeech TTSExecutor 失败: {e}")
                    raise Exception(f"PaddleSpeech 初始化失败: {e}")
            
            executor = self._paddlespeech_executors[cache_key]

        try:
            await loop.run_in_executor(
                None,
                self._run_paddlespeech_synthesis,
                executor,
                text,
                am,
                voc,
                lang,
                spk_id,
                output_path
            )
        except Exception as e:
            logger.error(f"PaddleSpeech 合成失败: {e}")
            raise Exception(f"PaddleSpeech TTS 合成失败: {e}")

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise Exception("PaddleSpeech 生成的音频文件为空")

        return output_path

    def _init_paddlespeech_executor(self, am: str, voc: str, lang: str):
        """初始化 PaddleSpeech TTSExecutor（在后台线程中调用）"""
        import sys
        
        user_site_paths = []
        for path in sys.path[:]:
            if 'AppData\\Roaming\\Python' in path or 'AppData/Roaming/Python' in path:
                user_site_paths.append(path)
                sys.path.remove(path)
            elif os.path.expanduser('~/.local') in path:
                user_site_paths.append(path)
                sys.path.remove(path)
        
        from paddlespeech.cli.tts.infer import TTSExecutor
        executor = TTSExecutor()
        return executor

    def _run_paddlespeech_synthesis(self, executor, text: str, am: str, voc: str, lang: str, spk_id: Optional[int], output_path: str):
        """运行 PaddleSpeech 合成（在后台线程中调用）"""
        kwargs = {
            "text": text,
            "am": am,
            "voc": voc,
            "lang": lang,
            "output": output_path,
        }
        if spk_id is not None:
            kwargs["spk_id"] = spk_id
        
        executor(**kwargs)

# 全局语音服务实例
voice_service = VoiceService()

