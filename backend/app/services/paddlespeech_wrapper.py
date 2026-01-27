"""
PaddleSpeech TTS 包装脚本

用于在子进程中调用 PaddleSpeech，避免 CLI 模块导入问题。
"""
import sys
import argparse
from paddlespeech.cli.tts.infer import TTSExecutor


def main():
    parser = argparse.ArgumentParser(description="PaddleSpeech TTS wrapper")
    parser.add_argument("--input", required=True, help="Input text")
    parser.add_argument("--am", required=True, help="Acoustic model")
    parser.add_argument("--voc", required=True, help="Vocoder")
    parser.add_argument("--lang", default="zh", help="Language")
    parser.add_argument("--output", required=True, help="Output WAV file path")
    parser.add_argument("--spk_id", type=int, default=None, help="Speaker ID (optional)")
    
    args = parser.parse_args()
    
    try:
        print(f"[INFO] 初始化 TTSExecutor (am={args.am}, voc={args.voc})...", file=sys.stderr)
        print("[INFO] 首次运行会下载模型，可能需要几分钟，请耐心等待...", file=sys.stderr)
        executor = TTSExecutor()
        print(f"[INFO] 开始合成语音: {args.input[:50]}...", file=sys.stderr)
        executor(
            text=args.input,
            am=args.am,
            voc=args.voc,
            lang=args.lang,
            spk_id=args.spk_id,
            output=args.output,
        )
        print(f"Success: Generated {args.output}", file=sys.stderr)
    except Exception as e:
        import traceback
        print(f"Error: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

