"""
PaddleSpeech TTS API 集成测试脚本

运行前确保：
1. 后端服务已启动: python -m uvicorn main:app --host 0.0.0.0 --port 18000
2. .env 中已配置: LOCAL_TTS_ENABLED=true

运行：
  cd backend
  python test_api_integration.py
"""

import requests
import os
import json
from pathlib import Path

BASE_URL = "http://localhost:18000"
API_URL = f"{BASE_URL}/api/v1/voice/synthesize"


def test_tts_api(text: str, voice: str = None, output_file: str = None):
    """测试 TTS API"""
    data = {"text": text}
    if voice:
        data["voice"] = voice
    
    print(f"\n{'='*60}")
    print(f"[测试] 文本: {text}")
    if voice:
        print(f"[测试] 音色: {voice}")
    print(f"[测试] 请求: POST {API_URL}")
    print(f"[测试] 数据: {json.dumps(data, ensure_ascii=False)}")
    
    try:
        response = requests.post(API_URL, json=data, timeout=120)
        
        if response.status_code == 200:
            if not output_file:
                output_file = f"test_api_{voice or 'default'}.wav"
            
            with open(output_file, "wb") as f:
                f.write(response.content)
            
            file_size = os.path.getsize(output_file)
            print(f"[✓ 成功] 音频已保存: {output_file}")
            print(f"[✓ 成功] 文件大小: {file_size} bytes ({file_size/1024:.2f} KB)")
            return True
        else:
            print(f"[✗ 失败] HTTP {response.status_code}")
            print(f"[✗ 失败] 响应: {response.text}")
            return False
    except requests.exceptions.ConnectionError:
        print("[✗ 错误] 无法连接到后端服务")
        print("[提示] 请确保后端服务已启动: python -m uvicorn main:app --host 0.0.0.0 --port 18000")
        return False
    except Exception as e:
        print(f"[✗ 错误] {e}")
        return False


def check_backend_status():
    """检查后端服务状态"""
    try:
        response = requests.get(f"{BASE_URL}/docs", timeout=5)
        return response.status_code == 200
    except:
        return False


def main():
    print("=" * 60)
    print("PaddleSpeech TTS API 集成测试")
    print("=" * 60)
    
    # 检查后端服务
    print("\n[检查] 后端服务状态...")
    if not check_backend_status():
        print("[✗ 失败] 后端服务未运行或无法访问")
        print("[提示] 请先启动后端服务:")
        print("  cd backend")
        print("  python -m uvicorn main:app --host 0.0.0.0 --port 18000")
        return
    print("[✓ 成功] 后端服务运行正常")
    
    # 测试 1: 使用默认音色
    print("\n" + "=" * 60)
    print("测试 1: 使用默认音色（不指定 voice）")
    print("=" * 60)
    test_tts_api(
        text="你好，这是 PaddleSpeech 离线语音合成测试。",
        output_file="test_api_default.wav"
    )
    
    # 测试 2: 指定音色
    print("\n" + "=" * 60)
    print("测试 2: 指定音色（fastspeech2_csmsc）")
    print("=" * 60)
    test_tts_api(
        text="这是指定音色的测试。",
        voice="fastspeech2_csmsc",
        output_file="test_api_fastspeech2_csmsc.wav"
    )
    
    # 测试 3: 长文本
    print("\n" + "=" * 60)
    print("测试 3: 长文本测试")
    print("=" * 60)
    test_tts_api(
        text="欢迎来到 AI 导游系统。这是一个基于 PaddleSpeech 的离线语音合成测试。系统支持多种音色配置，可以满足不同场景的需求。",
        voice="fastspeech2_csmsc",
        output_file="test_api_long.wav"
    )
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    print("\n生成的音频文件:")
    for wav_file in Path(".").glob("test_api_*.wav"):
        size = wav_file.stat().st_size
        print(f"  - {wav_file.name} ({size/1024:.2f} KB)")


if __name__ == "__main__":
    main()

