"""
Bert-VITS2 TTS 服务包装器
"""
import os
import sys
import tempfile
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 添加 Bert-VITS2 项目路径到 sys.path
BERT_VITS2_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "Bert-VITS2")
if BERT_VITS2_PATH not in sys.path:
    sys.path.insert(0, BERT_VITS2_PATH)

class BertVITS2Service:
    """Bert-VITS2 TTS 服务"""
    
    def __init__(self):
        self.net_g = None
        self.hps = None
        self.device = None
        self.speaker_ids = None
        self.speakers = None
        self._initialized = False
    
    def initialize(self, config_path: str, model_path: str, device: str = "cpu"):
        """初始化 Bert-VITS2 模型
        
        Args:
            config_path: 配置文件路径（config.json）
            model_path: 模型文件路径（.pth）
            device: 设备（cpu/cuda）
        """
        if self._initialized:
            logger.info("Bert-VITS2 已初始化，跳过重复初始化")
            return
        
        try:
            import torch
            import utils
            from infer import get_net_g, latest_version
            
            self.device = device if torch.cuda.is_available() and device == "cuda" else "cpu"
            logger.info(f"使用设备: {self.device}")
            
            self.hps = utils.get_hparams_from_file(config_path)
            version = self.hps.version if hasattr(self.hps, "version") else latest_version
            
            logger.info(f"加载 Bert-VITS2 模型: {model_path} (版本: {version})")
            self.net_g = get_net_g(model_path, version, self.device, self.hps)
            
            self.speaker_ids = self.hps.data.spk2id
            self.speakers = list(self.speaker_ids.keys())
            self._initialized = True
            
            logger.info(f"Bert-VITS2 初始化成功，可用说话人: {self.speakers}")
        except Exception as e:
            logger.error(f"Bert-VITS2 初始化失败: {e}")
            raise
    
    def synthesize(
        self,
        text: str,
        speaker: Optional[str] = None,
        language: str = "ZH",
        sdp_ratio: float = 0.5,
        noise_scale: float = 0.6,
        noise_scale_w: float = 0.8,
        length_scale: float = 1.0,
        output_path: Optional[str] = None,
    ) -> str:
        """合成语音
        
        Args:
            text: 要合成的文本
            speaker: 说话人名称（如果为 None，使用第一个可用说话人）
            language: 语言（ZH/JP/EN）
            sdp_ratio: SDP 比率
            noise_scale: 噪声比例
            noise_scale_w: 噪声比例 w
            length_scale: 长度比例
            output_path: 输出文件路径（如果为 None，自动生成）
        
        Returns:
            输出音频文件路径
        """
        import torch
        import soundfile as sf
        from infer import infer
        
        if not self._initialized:
            raise RuntimeError("Bert-VITS2 未初始化，请先调用 initialize()")
        
        if not output_path:
            output_path = tempfile.mktemp(suffix=".wav")
        
        if speaker is None or speaker not in self.speakers:
            speaker = self.speakers[0] if self.speakers else None
            if speaker is None:
                raise ValueError("没有可用的说话人")
            logger.warning(f"说话人未指定或不存在，使用默认说话人: {speaker}")
        
        try:
            logger.info(f"Bert-VITS2 合成: {text[:50]}... (说话人: {speaker}, 语言: {language})")
            
            with torch.no_grad():
                audio = infer(
                    text=text,
                    emotion=0,
                    sdp_ratio=sdp_ratio,
                    noise_scale=noise_scale,
                    noise_scale_w=noise_scale_w,
                    length_scale=length_scale,
                    sid=speaker,
                    language=language,
                    hps=self.hps,
                    net_g=self.net_g,
                    device=self.device,
                    reference_audio=None,
                    skip_start=False,
                    skip_end=False,
                    style_text=None,
                    style_weight=0.7,
                )
            
            sampling_rate = self.hps.data.sampling_rate
            sf.write(output_path, audio, sampling_rate)
            
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise Exception("生成的音频文件为空")
            
            logger.info(f"Bert-VITS2 合成成功: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Bert-VITS2 合成失败: {e}")
            raise Exception(f"Bert-VITS2 合成失败: {e}")

# 全局服务实例
bertvits2_service = BertVITS2Service()

