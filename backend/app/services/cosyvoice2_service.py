"""
CosyVoice2 TTS 服务包装器
CosyVoice2 是阿里巴巴达摩院推出的高质量 TTS 模型
"""
import os
import tempfile
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class CosyVoice2Service:
    """CosyVoice2 TTS 服务"""
    
    def __init__(self):
        self.model = None
        self.processor = None
        self.device = None
        self._initialized = False
    
    def initialize(self, model_path: Optional[str] = None, device: str = "cpu"):
        """初始化 CosyVoice2 模型
        
        Args:
            model_path: 模型路径（可选，如果为 None 则从 ModelScope/HuggingFace 加载）
            device: 设备（cpu/cuda）
        """
        if self._initialized:
            logger.info("CosyVoice2 已初始化，跳过重复初始化")
            return
        
        try:
            import torch
            from modelscope import snapshot_download
            from transformers import AutoModel, AutoProcessor
            
            self.device = device if torch.cuda.is_available() and device == "cuda" else "cpu"
            logger.info("使用设备: %s", self.device)
            
            # CosyVoice2 模型 ID（ModelScope）
            model_id = "iic/CosyVoice-300M"  # 默认使用 300M 版本
            
            if model_path and os.path.exists(model_path):
                # 使用本地模型路径
                logger.info(f"从本地路径加载 CosyVoice2 模型: {model_path}")
                model_dir = model_path
            else:
                # 从 ModelScope 下载模型（首次使用）
                logger.info(f"从 ModelScope 加载 CosyVoice2 模型: {model_id}")
                try:
                    model_dir = snapshot_download(model_id, cache_dir=model_path if model_path else None)
                except Exception as e:
                    logger.warning(f"从 ModelScope 下载失败，尝试使用 HuggingFace: {e}")
                    # 备用方案：使用 HuggingFace
                    model_id = "FunAudioLLM/CosyVoice-300M"
                    from huggingface_hub import snapshot_download as hf_snapshot_download
                    model_dir = hf_snapshot_download(
                        repo_id=model_id,
                        cache_dir=model_path if model_path else None
                    )
            
            logger.info(f"加载 CosyVoice2 模型: {model_dir}")
            
            # 加载处理器和模型
            self.processor = AutoProcessor.from_pretrained(model_dir, trust_remote_code=True)
            self.model = AutoModel.from_pretrained(model_dir, trust_remote_code=True)
            
            # 移动到指定设备
            self.model = self.model.to(self.device)
            self.model.eval()
            
            self._initialized = True
            logger.info("CosyVoice2 初始化成功")
            
        except ImportError as e:
            logger.error(f"CosyVoice2 依赖缺失: {e}")
            raise Exception(f"请安装 CosyVoice2 依赖: pip install modelscope transformers")
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
        import torch
        import soundfile as sf
        import numpy as np
        
        if not self._initialized:
            raise RuntimeError("CosyVoice2 未初始化，请先调用 initialize()")
        
        if not output_path:
            output_path = tempfile.mktemp(suffix=".wav")
        
        try:
            logger.info(f"CosyVoice2 合成: {text[:50]}... (语言: {language})")
            
            # 处理文本
            inputs = self.processor(
                text=text,
                return_tensors="pt",
            )
            
            # 移动到设备
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # 生成语音
            with torch.no_grad():
                output = self.model.generate(**inputs)
            
            # 提取音频数据
            if isinstance(output, dict):
                audio = output.get("audio", output.get("waveform"))
            else:
                audio = output
            
            # 转换为 numpy 数组
            if isinstance(audio, torch.Tensor):
                audio = audio.cpu().numpy()
            
            # 确保是 1D 数组
            if len(audio.shape) > 1:
                audio = audio.squeeze()
            
            # 获取采样率（CosyVoice2 通常为 24000 Hz）
            sample_rate = getattr(self.model.config, "sample_rate", 24000)
            
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

