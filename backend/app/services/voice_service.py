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
    """语音处理服务，支持 Whisper/Vosk 识别和 Edge TTS 合成"""
    
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
        
        # 使用传入的语音，如果没有则使用默认语音
        if not voice:
            voice = "zh-CN-XiaoxiaoNeural"
        
        # 再次清理文本，确保没有无效的 Unicode 字符和标点符号
        try:
            # 尝试编码为 UTF-8，过滤掉无效字符
            text = text.encode('utf-8', errors='ignore').decode('utf-8')
        except Exception as e:
            logger.warning(f"文本清理失败: {e}")
            # 如果编码失败，使用更严格的方式过滤
            text = ''.join(char for char in text if ord(char) < 0x110000 and not (0xD800 <= ord(char) <= 0xDFFF))
        
        # 移除所有标点符号，只保留中文、数字和空格
        text = re.sub(r"[^\u4e00-\u9fff0-9\s]", "", text)
        # 将多个连续空格替换为单个空格
        text = re.sub(r"\s+", " ", text)
        text = text.strip()
        
        # 重试机制：最多重试 5 次，针对连接错误增加重试
        max_retries = 5
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # 设置超时时间（30秒）
                communicate = edge_tts.Communicate(text, voice)
                await asyncio.wait_for(communicate.save(output_path), timeout=30.0)
                
                # 检查文件是否成功生成
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
                
                # 如果是编码错误，尝试清理文本后重试
                if "surrogates not allowed" in error_msg or "codec can't encode" in error_msg:
                    if attempt < max_retries - 1:
                        logger.info("检测到编码错误，清理文本后重试...")
                        # 更严格的文本清理：移除所有代理对字符
                        text = ''.join(
                            char for char in text 
                            if ord(char) < 0x110000 and not (0xD800 <= ord(char) <= 0xDFFF)
                        )
                        # 移除所有 emoji 和特殊符号
                        text = re.sub(r'[\U0001F300-\U0001F9FF\U0001FA00-\U0001FAFF]', '', text)
                        text = re.sub(r'[\U00002700-\U000027BF]', '', text)
                        # 移除所有标点符号，只保留中文、数字和空格
                        text = re.sub(r"[^\u4e00-\u9fff0-9\s]", "", text)
                        text = re.sub(r"\s+", " ", text)
                        text = text.strip()
                        if not text.strip():
                            raise Exception("文本清理后为空，无法合成")
                        continue
            
            # 判断是否为连接错误
            is_connection_error = (
                "Cannot connect" in error_msg or 
                "远程主机强迫关闭" in error_msg or
                "Connection" in error_msg or
                "timeout" in error_msg.lower() or
                "timed out" in error_msg.lower()
            )
            
            if attempt < max_retries - 1:
                # 根据错误类型调整等待时间
                if is_connection_error:
                    # 连接错误：使用更长的等待时间（2秒、4秒、8秒、16秒）
                    wait_time = 2.0 * (2 ** attempt)
                    logger.info(f"检测到连接错误，等待 {wait_time:.1f} 秒后重试...")
                else:
                    # 其他错误：使用较短的等待时间（指数退避）
                    wait_time = 0.5 * (2 ** attempt)
                
                await asyncio.sleep(wait_time)
            else:
                # 最后一次尝试失败，抛出更友好的错误
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
        
        # 理论上不会到达这里
        raise Exception(f"Edge TTS 合成失败: {last_error}")

    async def synthesize_local_paddlespeech(
        self,
        text: str,
        output_path: Optional[str] = None,
        voice: Optional[str] = None,
    ) -> str:
        """
        离线本地 TTS（PaddleSpeech）。

        通过命令行调用 PaddleSpeech CLI（paddlespeech tts），输出 wav。
        voice: 使用 settings.paddlespeech_voices 的 key；找不到则回退到 settings.PADDLESPEECH_DEFAULT_VOICE
        """
        import asyncio
        import sys

        if not output_path:
            output_path = tempfile.mktemp(suffix=".wav")

        voices = settings.paddlespeech_voices
        voice_key = voice if (voice and voice in voices) else settings.PADDLESPEECH_DEFAULT_VOICE
        cfg = voices.get(voice_key, {})

        # 常用参数：am(声学模型) / voc(声码器) / lang
        am = cfg.get("am", voice_key)
        voc = cfg.get("voc", "pwgan_csmsc")
        lang = cfg.get("lang", "zh")
        spk_id = cfg.get("spk_id", None)

        # 默认用当前环境 python，避免误用 base python
        py = settings.PADDLESPEECH_PYTHON or sys.executable

        # 使用包装脚本调用 PaddleSpeech（避免 paddlespeech.cli.tts 没有 __main__.py 的问题）
        wrapper_script = os.path.join(os.path.dirname(__file__), "paddlespeech_wrapper.py")
        cmd = [
            py,
            wrapper_script,
            "--input",
            text,
            "--am",
            str(am),
            "--voc",
            str(voc),
            "--lang",
            str(lang),
            "--output",
            output_path,
        ]
        if spk_id is not None:
            cmd += ["--spk_id", str(spk_id)]

        # 关键：禁用用户级 site-packages（Windows 下会把 win32/timer.pyd 注入 sys.path，导致 PaddleSpeech 导入失败）
        env = os.environ.copy()
        env["PYTHONNOUSERSITE"] = "1"

        logger.info(f"PaddleSpeech TTS 调用: {' '.join(cmd)}")
        logger.info("注意: 首次运行会下载模型（可能较慢，请耐心等待）...")
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            out_text = (stdout or b"").decode("utf-8", errors="ignore").strip()
            err_text = (stderr or b"").decode("utf-8", errors="ignore").strip()
            raise Exception(f"PaddleSpeech TTS 失败 (code={proc.returncode}): {err_text or out_text or 'unknown error'}")

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise Exception("PaddleSpeech 生成的音频文件为空")

        return output_path

# 全局语音服务实例
voice_service = VoiceService()

