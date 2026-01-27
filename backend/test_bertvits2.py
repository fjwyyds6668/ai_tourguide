"""
Bert-VITS2 TTS 测试脚本

运行：
  cd backend
  python test_bertvits2.py --text "你好，我是测试"
  
说明：
- 需要先配置 Bert-VITS2 模型路径（在 .env 中设置 BERTVITS2_CONFIG_PATH 和 BERTVITS2_MODEL_PATH）
- voice 参数是说话人名称（可选，默认使用配置中的默认说话人）
- 首次运行会加载模型（可能较慢），后续调用会使用已加载的模型，速度更快
"""

import argparse
import asyncio
import os
import time
import logging

from app.services.voice_service import voice_service
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run(text: str, voice: str | None, out_path: str | None):
    """运行 Bert-VITS2 TTS 测试"""
    out = out_path or "test_bertvits2.wav"
    if not os.path.isabs(out):
        out = os.path.abspath(out)

    config_path = settings.BERTVITS2_CONFIG_PATH
    model_path = settings.BERTVITS2_MODEL_PATH
    device = settings.BERTVITS2_DEVICE
    default_speaker = settings.BERTVITS2_DEFAULT_SPEAKER
    language = settings.BERTVITS2_LANGUAGE
    
    # 将相对路径转换为绝对路径（相对于项目根目录）
    if config_path and not os.path.isabs(config_path):
        # backend 目录的父目录是项目根目录
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(backend_dir, config_path)
    if model_path and not os.path.isabs(model_path):
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        model_path = os.path.join(backend_dir, model_path)

    logger.info("[INFO] 开始 Bert-VITS2 TTS 合成...")
    logger.info(f"[INFO] 文本: {text}")
    logger.info(f"[INFO] 配置文件: {config_path}")
    logger.info(f"[INFO] 模型文件: {model_path}")
    logger.info(f"[INFO] 设备: {device}")
    logger.info(f"[INFO] 语言: {language}")
    logger.info(f"[INFO] 说话人: {voice or default_speaker or '默认'}")
    logger.info("[INFO] 注意: 首次运行会加载模型（可能较慢，请耐心等待）...")
    logger.info("[INFO] 提示: 后续调用会使用已加载的模型，速度会快很多")
    
    start_time = time.time()
    
    try:
        wav_path = await voice_service.synthesize_local_bertvits2(
            text=text, 
            voice=voice, 
            output_path=out
        )
        
        elapsed_time = time.time() - start_time
        
        logger.info("\n[OK] Bert-VITS2 TTS 合成成功")
        logger.info(f" - 说话人: {voice or default_speaker or '默认'}")
        logger.info(f" - 输出文件: {wav_path}")
        logger.info(f" - 耗时: {elapsed_time:.2f} 秒")
        
        # 显示文件大小
        if os.path.exists(wav_path):
            size = os.path.getsize(wav_path)
            logger.info(f" - 文件大小: {size} bytes ({size/1024:.2f} KB)")
        
        # 性能提示
        if elapsed_time > 10:
            logger.info("\n[提示] 首次调用较慢是因为需要加载模型")
            logger.info("       后续调用会使用已加载的模型，速度会快很多（预计 1-3 秒）")
        else:
            logger.info("\n[提示] 速度正常，模型已加载")
            
    except Exception as e:
        error_str = str(e)
        elapsed_time = time.time() - start_time
        
        logger.error(f"\n[ERROR] Bert-VITS2 TTS 合成失败（耗时: {elapsed_time:.2f} 秒）")
        logger.error(f"错误详情: {error_str}")
        
        # 常见错误诊断
        if "未初始化" in error_str or "配置文件" in error_str or "模型文件" in error_str:
            logger.error("\n" + "="*60)
            logger.error("[诊断] 配置问题")
            logger.error("="*60)
            logger.error("\n问题: Bert-VITS2 配置路径或模型路径未设置或不存在")
            logger.error("\n[解决方案]")
            logger.error("1. 检查 .env 文件中的配置：")
            logger.error("   BERTVITS2_CONFIG_PATH=Bert-VITS2/configs/config.json")
            logger.error("   BERTVITS2_MODEL_PATH=Bert-VITS2/models/G_latest.pth")
            logger.error("2. 确保配置文件存在：")
            logger.error(f"   - 配置文件: {config_path}")
            logger.error(f"   - 模型文件: {model_path}")
            logger.error("3. 确保 Bert-VITS2 项目已正确克隆到项目根目录")
            logger.error("="*60)
        elif "No module named" in error_str or "cannot import" in error_str:
            logger.error("\n" + "="*60)
            logger.error("[诊断] 依赖未安装")
            logger.error("="*60)
            logger.error("\n问题: Bert-VITS2 依赖未正确安装")
            logger.error("\n[解决方案]")
            logger.error("1. 安装依赖：")
            logger.error("   pip install torch soundfile librosa pypinyin cn2an pyyaml")
            logger.error("2. 如果使用 GPU，确保安装了 CUDA 版本的 PyTorch")
            logger.error("="*60)
        else:
            logger.error("\n[提示] 请检查错误信息并确保 Bert-VITS2 正确配置")
        
        raise


def main():
    parser = argparse.ArgumentParser(description="Bert-VITS2 TTS 测试脚本")
    parser.add_argument(
        "--text", 
        default="你好，我是 Bert-VITS2 TTS 测试。", 
        help="要合成的文本"
    )
    parser.add_argument(
        "--voice", 
        default=None, 
        help="说话人名称（可选，默认从 .env 读取）"
    )
    parser.add_argument(
        "--out", 
        default="test_bertvits2.wav", 
        help="输出 wav 路径（默认：test_bertvits2.wav）"
    )
    args = parser.parse_args()

    asyncio.run(run(args.text, args.voice, args.out))


if __name__ == "__main__":
    main()

