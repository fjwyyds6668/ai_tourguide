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
    """语音处理服务，支持 Whisper/Vosk 识别和科大讯飞 TTS/本地 TTS（CosyVoice2）合成"""
    
    def __init__(self):
        self.whisper_model = None
        self.vosk_model = None
        self._ffmpeg_available = self._check_ffmpeg()
        self._init_models()
    
    def _check_ffmpeg(self) -> bool:
        """检查 ffmpeg 是否可用（Whisper 需要 ffmpeg）"""
        try:
            import subprocess
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                logger.info("ffmpeg 已安装并可用")
                return True
        except FileNotFoundError:
            logger.warning("ffmpeg 未安装或不在 PATH 中")
        except Exception as e:
            logger.warning(f"检查 ffmpeg 时出错: {e}")
        return False
    
    def _init_models(self):
        """初始化语音识别模型"""
        if not self._ffmpeg_available:
            logger.warning("ffmpeg 不可用，Whisper 语音识别功能将无法使用。请安装 ffmpeg：conda install -c conda-forge ffmpeg")
        
        try:
            import warnings
            import whisper
            # 抑制 FP16 在 CPU 上的警告（这是正常的回退行为）
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="FP16 is not supported on CPU")
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
            raise ValueError("Whisper 模型未加载")
        
        if not self._ffmpeg_available:
            raise Exception(
                "ffmpeg 未安装或不可用。Whisper 需要 ffmpeg 来处理音频文件。\n"
                "安装方法（Windows）：\n"
                "1. 使用 conda: conda install -c conda-forge ffmpeg\n"
                "2. 或下载 ffmpeg 并添加到系统 PATH: https://ffmpeg.org/download.html"
            )
        
        if not os.path.exists(audio_file_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_file_path}")
        
        file_size = os.path.getsize(audio_file_path)
        if file_size == 0:
            raise ValueError("音频文件为空")
        
        logger.info(f"开始 Whisper 识别: file={audio_file_path}, size={file_size} bytes")
        
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="FP16 is not supported on CPU")
                result = self.whisper_model.transcribe(audio_file_path, language="zh")
            
            text = result.get("text", "").strip()
            if not text:
                logger.warning("Whisper 识别结果为空")
                return ""
            
            logger.info(f"Whisper 识别成功: text_length={len(text)}")
            return text
        except FileNotFoundError as e:
            if "ffmpeg" in str(e).lower() or "系统找不到指定的文件" in str(e):
                logger.error("ffmpeg 未找到", exc_info=True)
                raise Exception(
                    "ffmpeg 未安装或不在系统 PATH 中。\n"
                    "安装方法（Windows）：\n"
                    "1. 使用 conda: conda install -c conda-forge ffmpeg\n"
                    "2. 或下载 ffmpeg 并添加到系统 PATH: https://ffmpeg.org/download.html"
                )
            raise
        except Exception as e:
            logger.error(f"Whisper 识别失败: {e}", exc_info=True)
            error_msg = str(e)
            if "ffmpeg" in error_msg.lower() or "系统找不到指定的文件" in error_msg:
                raise Exception(
                    "ffmpeg 未安装或不在系统 PATH 中。\n"
                    "安装方法（Windows）：\n"
                    "1. 使用 conda: conda install -c conda-forge ffmpeg\n"
                    "2. 或下载 ffmpeg 并添加到系统 PATH: https://ffmpeg.org/download.html"
                )
            raise Exception(f"Whisper 语音识别失败: {error_msg}")
    
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
    
    async def synthesize_xfyun(self, text: str, output_path: Optional[str] = None, voice: Optional[str] = None) -> str:
        """使用科大讯飞 WebSocket TTS 进行语音合成（带重试机制）
        
        Args:
            text: 要合成的文本
            output_path: 输出文件路径（可选，默认生成 wav）
            voice: 音色名称（可选，默认使用 settings.XFYUN_VOICE，如 x4_yezi、aisjiuxu 等）
        """
        import asyncio
        import base64
        import hashlib
        import hmac
        import json
        import ssl
        import threading
        import websocket
        import soundfile as sf
        import numpy as np
        from datetime import datetime
        from time import mktime
        from urllib.parse import urlencode
        from wsgiref.handlers import format_date_time
        
        if not output_path:
            output_path = tempfile.mktemp(suffix=".wav")
        
        if not voice:
            voice = settings.XFYUN_VOICE
        
        if not settings.XFYUN_APPID or not settings.XFYUN_API_KEY or not settings.XFYUN_API_SECRET:
            raise Exception(
                "科大讯飞 TTS 未配置：请在 .env 中设置 XFYUN_APPID、XFYUN_API_KEY 和 XFYUN_API_SECRET；"
                "或启用本地 TTS（LOCAL_TTS_ENABLED=true）作为备用。"
            )
        
        if not output_path:
            # 使用临时目录（通常在内存文件系统或SSD上，比默认位置更快）
            temp_dir = tempfile.gettempdir()
            output_path = tempfile.mktemp(suffix=".wav", dir=temp_dir)
        
        try:
            text = text.encode('utf-8', errors='ignore').decode('utf-8')
        except Exception as e:
            logger.warning(f"文本清理失败: {e}")
            text = ''.join(char for char in text if ord(char) < 0x110000 and not (0xD800 <= ord(char) <= 0xDFFF))
        
        # 简化文本清理：只移除明显无效字符，保留更多内容以提升合成质量
        # 移除控制字符和特殊符号，但保留常见标点
        text = re.sub(r"[\x00-\x1F\x7F-\x9F]", "", text)  # 移除控制字符
        text = re.sub(r"\s{2,}", " ", text)  # 合并多个空格
        text = text.strip()
        
        if not text:
            raise Exception("文本为空，无法合成")
        
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # 生成 WebSocket URL（参考 demo 的 Ws_Param.create_url）
                url = 'wss://tts-api.xfyun.cn/v2/tts'
                now = datetime.now()
                date = format_date_time(mktime(now.timetuple()))
                
                signature_origin = "host: " + "ws-api.xfyun.cn" + "\n"
                signature_origin += "date: " + date + "\n"
                signature_origin += "GET " + "/v2/tts " + "HTTP/1.1"
                
                signature_sha = hmac.new(
                    settings.XFYUN_API_SECRET.encode('utf-8'),
                    signature_origin.encode('utf-8'),
                    digestmod=hashlib.sha256
                ).digest()
                signature_sha = base64.b64encode(signature_sha).decode(encoding='utf-8')
                
                authorization_origin = f'api_key="{settings.XFYUN_API_KEY}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_sha}"'
                authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')
                
                v = {
                    "authorization": authorization,
                    "date": date,
                    "host": "ws-api.xfyun.cn"
                }
                ws_url = url + '?' + urlencode(v)
                
                # 准备请求数据
                common_args = {"app_id": settings.XFYUN_APPID}
                business_args = {
                    "aue": "raw",
                    "auf": "audio/L16;rate=16000",
                    "vcn": voice,
                    "tte": "utf8"
                }
                data_args = {
                    "status": 2,
                    "text": str(base64.b64encode(text.encode('utf-8')), "UTF8")
                }
                
                request_data = {
                    "common": common_args,
                    "business": business_args,
                    "data": data_args
                }
                
                # 使用线程池运行同步 WebSocket（websocket-client 是同步的）
                audio_data_list = []
                error_occurred = [False]
                error_message = [None]
                ws_closed = threading.Event()
                
                def on_message(ws, message):
                    try:
                        msg = json.loads(message)
                        code = msg.get("code", 0)
                        status = msg.get("data", {}).get("status", 0)
                        
                        if code != 0:
                            err_msg = msg.get("message", "未知错误")
                            error_occurred[0] = True
                            error_message[0] = f"科大讯飞 TTS 错误: code={code}, message={err_msg}"
                            logger.error(error_message[0])
                            ws.close()
                            return
                        
                        if status == 2:
                            ws_closed.set()
                            ws.close()
                            return
                        
                        audio_base64 = msg.get("data", {}).get("audio", "")
                        if audio_base64:
                            audio_bytes = base64.b64decode(audio_base64)
                            audio_data_list.append(audio_bytes)
                    except Exception as e:
                        error_occurred[0] = True
                        error_message[0] = f"解析消息失败: {e}"
                        logger.error(error_message[0])
                        ws.close()
                
                def on_error(ws, error):
                    error_occurred[0] = True
                    error_message[0] = f"WebSocket 错误: {error}"
                    logger.error(error_message[0])
                    ws_closed.set()
                
                def on_close(ws, close_status_code, close_msg):
                    ws_closed.set()
                
                def on_open(ws):
                    ws.send(json.dumps(request_data))
                    logger.info(f"科大讯飞 TTS 发送请求: {text[:50]}... (音色: {voice})")
                
                def run_websocket():
                    ws = websocket.WebSocketApp(
                        ws_url,
                        on_message=on_message,
                        on_error=on_error,
                        on_close=on_close
                    )
                    ws.on_open = on_open
                    # ping_interval/ping_timeout 保活；ping_timeout 需足够大，否则合成期间服务端忙时无法及时 pong 会触发 "ping/pong timed out"
                    # 注意：ping_interval 必须大于 ping_timeout
                    ws.run_forever(
                        sslopt={"cert_reqs": ssl.CERT_NONE},
                        ping_interval=30,
                        ping_timeout=25,
                        skip_utf8_validation=True,
                    )
                
                # 在线程中运行 WebSocket（同步阻塞）
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, run_websocket)
                
                # 等待 WebSocket 关闭（根据文本长度动态调整超时：每100字约6秒，最少20秒，最多90秒，避免长文本合成未完成就超时）
                text_len = len(text)
                timeout_seconds = max(20.0, min(90.0, (text_len / 100) * 6))
                if not ws_closed.wait(timeout=timeout_seconds):
                    raise Exception(f"科大讯飞 TTS 请求超时（{timeout_seconds:.1f}秒）")
                
                if error_occurred[0]:
                    raise Exception(error_message[0] or "科大讯飞 TTS 未知错误")
                
                if not audio_data_list:
                    raise Exception("科大讯飞 TTS 返回空音频数据")
                
                # 合并所有音频块
                pcm_data = b''.join(audio_data_list)
                
                # 将 PCM (16kHz, 16bit, mono) 转换为 numpy 数组
                audio_array = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
                
                # 保存为 WAV 文件
                sf.write(output_path, audio_array, 16000)
                
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    logger.info(f"科大讯飞 TTS 合成成功 (尝试 {attempt + 1}/{max_retries})")
                    return output_path
                raise Exception("生成的音频文件为空")
                    
            except asyncio.TimeoutError:
                last_error = Exception("科大讯飞 TTS 请求超时")
                error_msg = "请求超时 (timeout)"
                logger.warning(f"科大讯飞 TTS 尝试 {attempt + 1}/{max_retries} 超时")
            except Exception as e:
                last_error = e
                error_msg = str(e)
                logger.warning(f"科大讯飞 TTS 尝试 {attempt + 1}/{max_retries} 失败: {e}")
            
            is_connection_error = (
                "Cannot connect" in error_msg or 
                "远程主机强迫关闭" in error_msg or
                "Connection" in error_msg or
                "timeout" in error_msg.lower() or
                "timed out" in error_msg.lower() or
                "WebSocket" in error_msg or
                "SSL" in error_msg or
                "EOF" in error_msg
            )
            
            if attempt < max_retries - 1:
                if is_connection_error:
                    # 连接/SSL 错误时稍长等待，给网络恢复时间：1秒、2秒、4秒
                    wait_time = 1.0 * (2 ** attempt)
                    logger.info(f"检测到连接错误，等待 {wait_time:.1f} 秒后重试...")
                else:
                    # 其他错误快速重试：0.2秒、0.4秒、0.8秒
                    wait_time = 0.2 * (2 ** attempt)
                
                await asyncio.sleep(wait_time)
            else:
                if "401" in error_msg or "403" in error_msg or "鉴权" in error_msg:
                    raise Exception(
                        "科大讯飞 TTS 服务暂时不可用（鉴权失败或被拒绝）。"
                        "请检查 XFYUN_APPID / XFYUN_API_KEY / XFYUN_API_SECRET 是否正确，或检查网络/限制。"
                    )
                elif is_connection_error:
                    raise Exception(
                        f"科大讯飞 TTS 连接失败（已重试 {max_retries} 次）。"
                        "请检查网络连接或稍后重试。"
                        f"错误详情: {error_msg}"
                    )
                else:
                    raise Exception(f"科大讯飞 TTS 合成失败: {error_msg}")
        
        raise Exception(f"科大讯飞 TTS 合成失败: {last_error}")

    async def synthesize_local_cosyvoice2(
        self,
        text: str,
        output_path: Optional[str] = None,
        voice: Optional[str] = None,
    ) -> str:
        """
        离线本地 TTS（CosyVoice2）- 阿里巴巴达摩院高质量语音合成。

        voice: 说话人名称（可选）
        """
        import asyncio
        from app.services.cosyvoice2_service import cosyvoice2_service

        if not output_path:
            output_path = tempfile.mktemp(suffix=".wav")

        if not cosyvoice2_service._initialized:
            model_path = settings.COSYVOICE2_MODEL_PATH
            device = settings.COSYVOICE2_DEVICE
            
            # 将相对路径转换为绝对路径（如果提供了相对路径）
            if model_path and not os.path.isabs(model_path):
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                model_path = os.path.join(project_root, model_path)
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                cosyvoice2_service.initialize,
                model_path if model_path else None,
                device
            )

        speaker = voice or settings.COSYVOICE2_SPEAKER
        language = settings.COSYVOICE2_LANGUAGE

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                cosyvoice2_service.synthesize,
                text,
                speaker,
                language,
                output_path
            )
        except Exception as e:
            logger.error(f"CosyVoice2 合成失败: {e}")
            raise Exception(f"CosyVoice2 TTS 合成失败: {e}")

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise Exception("CosyVoice2 生成的音频文件为空")

        return output_path

# 全局语音服务实例
voice_service = VoiceService()

