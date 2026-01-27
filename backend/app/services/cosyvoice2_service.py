"""
CosyVoice2 TTS 服务包装器
CosyVoice2 是阿里巴巴达摩院推出的高质量 TTS 模型
"""
import os
import sys
import tempfile
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class CosyVoice2Service:
    """CosyVoice2 TTS 服务"""
    
    def __init__(self):
        self.cosyvoice = None
        self.device = None
        self._initialized = False
        self.sample_rate = 24000
    
    def initialize(self, model_path: Optional[str] = None, device: str = "cpu"):
        """初始化 CosyVoice2 模型
        
        Args:
            model_path: 模型路径（可选，如果为 None 则从 ModelScope 下载到缓存目录）
            device: 设备（cpu/cuda）
        """
        if self._initialized:
            logger.info("CosyVoice2 已初始化，跳过重复初始化")
            return
        
        try:
            import torch
            from modelscope import snapshot_download
            
            self.device = device if torch.cuda.is_available() and device == "cuda" else "cpu"
            logger.info("使用设备: %s", self.device)
            
            # 注意：iic/CosyVoice-300M（CosyVoice 1.0）并不是 HuggingFace Transformers 格式（没有 config.json）。
            # 正确的推理方式是使用 CosyVoice 官方仓库提供的 AutoModel：
            #   from cosyvoice.cli.cosyvoice import AutoModel
            # 并指向 snapshot_download 得到的 model_dir。

            model_id = "iic/CosyVoice-300M"
            if model_path and os.path.exists(model_path):
                model_dir = model_path
            else:
                logger.info("从 ModelScope 下载/使用缓存模型: %s", model_id)
                model_dir = snapshot_download(model_id, cache_dir=model_path if model_path else None)

            logger.info("CosyVoice 模型目录: %s", model_dir)

            # 定位 CosyVoice 代码（需要你克隆 CosyVoice 仓库到项目根目录 CosyVoice/，或安装 cosyvoice 包）
            # project_root = .../ai_tourguide
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            cosyvoice_repo = os.environ.get("COSYVOICE_REPO_PATH") or os.path.join(project_root, "CosyVoice")

            if os.path.isdir(cosyvoice_repo) and cosyvoice_repo not in sys.path:
                sys.path.insert(0, cosyvoice_repo)
                # CosyVoice README 要求把 third_party/Matcha-TTS 加到 sys.path
                matcha_path = os.path.join(cosyvoice_repo, "third_party", "Matcha-TTS")
                if os.path.isdir(matcha_path) and matcha_path not in sys.path:
                    sys.path.append(matcha_path)

            try:
                from cosyvoice.cli.cosyvoice import AutoModel  # type: ignore
            except Exception as e:
                raise Exception(
                    "CosyVoice2 初始化失败：未找到 CosyVoice 推理代码（cosyvoice.cli.cosyvoice.AutoModel）。\n"
                    "请将 CosyVoice 官方仓库克隆到项目根目录 `CosyVoice/`：\n"
                    "  git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git\n"
                    "并按仓库 requirements 安装依赖后重启后端。\n"
                    "（也可通过环境变量 COSYVOICE_REPO_PATH 指定仓库路径）\n"
                    f"原始错误: {e}"
                ) from e

            # 部分版本 AutoModel 支持 device 参数；不支持则退化为默认
            try:
                self.cosyvoice = AutoModel(model_dir=model_dir, device=self.device)
            except TypeError:
                self.cosyvoice = AutoModel(model_dir=model_dir)

            self.sample_rate = getattr(self.cosyvoice, "sample_rate", 24000)
            
            self._initialized = True
            logger.info("CosyVoice2 初始化成功")
            
        except ImportError as e:
            logger.error(f"CosyVoice2 依赖缺失: {e}")
            raise Exception("请安装 CosyVoice2 依赖: pip install modelscope")
        except Exception as e:
            logger.error(f"CosyVoice2 初始化失败: {e}")
            raise
    
    def synthesize(
        self,
        text: str,
        speaker: Optional[str] = None,
        language: str = "zh",
        output_path: Optional[str] = None,
    ) -> str:
        """合成语音
        
        Args:
            text: 要合成的文本
            speaker: 说话人（可选，CosyVoice2 支持多说话人）
            language: 语言（zh/en/ja 等）
            output_path: 输出文件路径（如果为 None，自动生成）
        
        Returns:
            输出音频文件路径
        """
        import soundfile as sf
        import numpy as np
        
        if not self._initialized:
            raise RuntimeError("CosyVoice2 未初始化，请先调用 initialize()")
        
        if not output_path:
            output_path = tempfile.mktemp(suffix=".wav")
        
        try:
            logger.info("CosyVoice2 合成: %s... (语言: %s)", text[:50], language)

            if self.cosyvoice is None:
                raise RuntimeError("CosyVoice2 模型未正确初始化")

            # zero-shot 默认提示（如需自定义，可通过环境变量覆盖）
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            cosyvoice_repo = os.environ.get("COSYVOICE_REPO_PATH") or os.path.join(project_root, "CosyVoice")

            prompt_wav = os.environ.get("COSYVOICE_PROMPT_WAV", "").strip()
            if not prompt_wav:
                prompt_wav = os.path.join(cosyvoice_repo, "asset", "zero_shot_prompt.wav")

            prompt_text = os.environ.get("COSYVOICE_PROMPT_TEXT", "").strip() or "希望你以后能够做的比我还好呦。"

            if not os.path.exists(prompt_wav):
                raise Exception(
                    f"未找到 CosyVoice zero-shot 提示音频: {prompt_wav}\n"
                    "请从 CosyVoice 仓库的 asset/zero_shot_prompt.wav 提供该文件，\n"
                    "或设置环境变量 COSYVOICE_PROMPT_WAV 指向一个本地 wav 作为参考音频。"
                )

            # 生成语音：取第一段结果
            audio_tensor = None
            for _i, out in enumerate(self.cosyvoice.inference_zero_shot(text, prompt_text, prompt_wav)):
                audio_tensor = out.get("tts_speech")
                break

            if audio_tensor is None:
                raise Exception("CosyVoice 未返回 tts_speech")

            # torch.Tensor -> numpy
            try:
                audio = audio_tensor.detach().cpu().numpy()
            except Exception:
                audio = np.asarray(audio_tensor)

            if len(audio.shape) > 1:
                audio = audio.squeeze()

            sample_rate = int(self.sample_rate or 24000)
            
            # 归一化音频数据到 [-1, 1]
            if audio.dtype != np.float32:
                audio = audio.astype(np.float32)
            if audio.max() > 1.0 or audio.min() < -1.0:
                audio = audio / np.max(np.abs(audio))
            
            # 保存音频文件
            sf.write(output_path, audio, sample_rate)
            
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise Exception("生成的音频文件为空")
            
            logger.info(f"CosyVoice2 合成成功: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"CosyVoice2 合成失败: {e}")
            raise Exception(f"CosyVoice2 合成失败: {e}")

# 全局服务实例
cosyvoice2_service = CosyVoice2Service()

