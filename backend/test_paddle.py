"""
PaddleSpeech TTS 测试脚本

运行：
  cd backend
  python test_paddle.py --text "你好，我是测试"
  
说明：
- 需要先安装 PaddleSpeech：pip install paddlepaddle paddlespeech
- voice 参数是 backend/.env 里 PADDLESPEECH_VOICES_JSON 的 key（可选）
- 首次运行会下载模型（可能较慢），后续调用会使用缓存的模型，速度更快
"""

import argparse
import asyncio
import os
import time

from app.services.voice_service import voice_service
from app.core.config import settings


async def run(text: str, voice: str | None, out_path: str | None):
    """运行 PaddleSpeech TTS 测试"""
    out = out_path or "test_paddle.wav"
    if not os.path.isabs(out):
        out = os.path.abspath(out)

    voices = settings.paddlespeech_voices
    voice_key = voice if (voice and voice in voices) else settings.PADDLESPEECH_DEFAULT_VOICE
    cfg = voices.get(voice_key, {})
    am = cfg.get("am", voice_key)
    voc = cfg.get("voc", "pwgan_csmsc")
    lang = cfg.get("lang", "zh")

    print("[INFO] 开始 PaddleSpeech TTS 合成...")
    print(f"[INFO] 文本: {text}")
    print(f"[INFO] 音色: {voice_key}")
    print(f"[INFO] 声学模型 (AM): {am}")
    print(f"[INFO] 声码器 (VOC): {voc}")
    print(f"[INFO] 语言: {lang}")
    print("[INFO] 注意: 首次运行会下载模型（可能较慢，请耐心等待）...")
    print("[INFO] 提示: 后续调用会使用缓存的模型，速度会快很多")
    
    start_time = time.time()
    
    try:
        wav_path = await voice_service.synthesize_local_paddlespeech(
            text=text, 
            voice=voice, 
            output_path=out
        )
        
        elapsed_time = time.time() - start_time
        
        print("\n[OK] PaddleSpeech TTS 合成成功")
        print(f" - 音色: {voice_key}")
        print(f" - 声学模型: {am}")
        print(f" - 声码器: {voc}")
        print(f" - 输出文件: {wav_path}")
        print(f" - 耗时: {elapsed_time:.2f} 秒")
        
        # 显示文件大小
        if os.path.exists(wav_path):
            size = os.path.getsize(wav_path)
            print(f" - 文件大小: {size} bytes ({size/1024:.2f} KB)")
        
        # 性能提示
        if elapsed_time > 5:
            print("\n[提示] 首次调用较慢是因为需要加载模型")
            print("       后续调用会使用缓存的模型，速度会快很多（预计 0.5-2 秒）")
        else:
            print("\n[提示] 速度正常，模型已缓存")
            
    except Exception as e:
        error_str = str(e)
        elapsed_time = time.time() - start_time
        
        print(f"\n[ERROR] PaddleSpeech TTS 合成失败（耗时: {elapsed_time:.2f} 秒）")
        print(f"错误详情: {error_str}")
        
        # 常见错误诊断
        if "No module named" in error_str or "cannot import" in error_str:
            print("\n" + "="*60)
            print("[诊断] 模块导入失败")
            print("="*60)
            print("\n问题: PaddleSpeech 未正确安装")
            print("\n[解决方案]")
            print("1. 安装 PaddleSpeech:")
            print("   pip install paddlepaddle paddlespeech")
            print("2. 如果安装失败，尝试:")
            print("   pip install paddlepaddle -i https://pypi.tuna.tsinghua.edu.cn/simple")
            print("   pip install paddlespeech -i https://pypi.tuna.tsinghua.edu.cn/simple")
            print("3. 检查 Python 环境是否正确")
            print("="*60)
        elif "download" in error_str.lower() or "model" in error_str.lower():
            print("\n[提示] 可能是模型下载问题，请检查网络连接")
        else:
            print("\n[提示] 请检查错误信息并确保 PaddleSpeech 正确安装")
        
        raise


def main():
    parser = argparse.ArgumentParser(description="PaddleSpeech TTS 测试脚本")
    parser.add_argument(
        "--text", 
        default="你好，我是 PaddleSpeech TTS 测试。", 
        help="要合成的文本"
    )
    parser.add_argument(
        "--voice", 
        default=None, 
        help="音色 key（可选，默认从 .env 读取）。例如: fastspeech2_csmsc"
    )
    parser.add_argument(
        "--out", 
        default="test_paddle.wav", 
        help="输出 wav 路径（默认：test_paddle.wav）"
    )
    args = parser.parse_args()

    asyncio.run(run(args.text, args.voice, args.out))


if __name__ == "__main__":
    main()

