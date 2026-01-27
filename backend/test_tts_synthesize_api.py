"""
测试后端 /voice/synthesize 接口（用于验证 CosyVoice2 离线 TTS 是否生效）

使用前提：
- 后端服务已启动（FastAPI）
- .env 中配置：
  LOCAL_TTS_ENABLED=true
  LOCAL_TTS_ENGINE=cosyvoice2
  （可选）LOCAL_TTS_FORCE=true  # 强制走本地，避免 Edge TTS 影响
"""

import os
import sys
import asyncio

import httpx


def _get_base_url() -> str:
    # 允许通过环境变量覆盖，便于不同端口/部署方式
    # 例如：set TTS_API_BASE_URL=http://127.0.0.1:8000
    # 本项目 backend/main.py 默认端口为 18000
    return os.environ.get("TTS_API_BASE_URL", "http://127.0.0.1:18000").rstrip("/")


async def main():
    base_url = _get_base_url()
    # backend/main.py: app.include_router(router, prefix="/api/v1")
    health_url = f"{base_url}/health"
    url = f"{base_url}/api/v1/voice/synthesize"

    payload = {
        "text": "这是一个离线 CosyVoice2 的接口测试，如果你听到这段语音说明部署成功。",
        "voice": None,
        "character_id": None,
    }

    print("=" * 60)
    print("TTS /voice/synthesize 接口测试")
    print("=" * 60)
    print(f"请求地址: {url}")
    print(f"测试文本: {payload['text']}")

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            health = await client.get(health_url)
            health.raise_for_status()
        except Exception as e:
            raise RuntimeError(
                f"无法连接后端服务: {health_url}\n"
                f"请确认后端已启动且端口正确；或设置环境变量 TTS_API_BASE_URL。\n"
                f"原始错误: {e}"
            ) from e

        resp = await client.post(url, json=payload)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        ext = ".wav" if "audio/wav" in content_type else ".mp3"
        out_path = os.path.join(os.path.dirname(__file__), f"tts_api_test{ext}")

        with open(out_path, "wb") as f:
            f.write(resp.content)

    size_kb = os.path.getsize(out_path) / 1024
    print(f"\n✅ 成功，已保存: {out_path} ({size_kb:.2f} KB)")
    print("如果你配置了 LOCAL_TTS_FORCE=true，可确保一定走离线 TTS。")


if __name__ == "__main__":
    # 兼容从项目根目录执行：python backend/test_tts_synthesize_api.py
    sys.path.insert(0, os.path.dirname(__file__))
    asyncio.run(main())


