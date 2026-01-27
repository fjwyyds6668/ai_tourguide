"""
PaddleSpeech 离线 TTS 自检脚本

运行：
  cd backend
  python test_paddlespeech_tts.py --text "你好，我是离线语音测试" --voice fastspeech2_csmsc --out test_paddle.wav

说明：
- 需要先安装 PaddleSpeech（并在同一个 python 环境里）：
    pip install paddlespeech paddlepaddle
- voice 参数是 backend/.env 里 PADDLESPEECH_VOICES_JSON 的 key（可选）
"""

import argparse
import asyncio
import os

from app.services.voice_service import voice_service
from app.core.config import settings


async def run(text: str, voice: str | None, out_path: str | None):
    out = out_path
    if out and not os.path.isabs(out):
        out = os.path.abspath(out)

    print("[INFO] 开始 PaddleSpeech TTS 合成...")
    print(f"[INFO] 文本: {text}")
    print(f"[INFO] 音色: {voice or settings.PADDLESPEECH_DEFAULT_VOICE}")
    print("[INFO] 注意: 首次运行会下载模型（可能较慢，请耐心等待）...")
    
    try:
        wav_path = await voice_service.synthesize_local_paddlespeech(text=text, voice=voice, output_path=out)
        print("[OK] PaddleSpeech TTS success")
        print(" - voice:", voice or settings.PADDLESPEECH_DEFAULT_VOICE)
        print(" - wav  :", wav_path)
    except Exception as e:
        print(f"[ERROR] PaddleSpeech TTS 失败: {e}")
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", default="你好，我是离线语音合成测试。")
    parser.add_argument("--voice", default=None, help="PADDLESPEECH_VOICES_JSON 的 key（可选）")
    parser.add_argument("--out", default="test_paddle.wav", help="输出 wav 路径（默认：test_paddle.wav）")
    args = parser.parse_args()

    asyncio.run(run(args.text, args.voice, args.out))


if __name__ == "__main__":
    main()


