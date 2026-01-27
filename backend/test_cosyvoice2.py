"""
测试 CosyVoice2 TTS
"""
import os
import sys
import asyncio

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

from app.services.voice_service import voice_service
from app.core.config import settings

async def test_cosyvoice2():
    """测试 CosyVoice2 TTS"""
    print("=" * 60)
    print("CosyVoice2 TTS 测试")
    print("=" * 60)
    
    # 检查配置
    print(f"\n📋 配置信息:")
    print(f"   LOCAL_TTS_ENABLED: {settings.LOCAL_TTS_ENABLED}")
    print(f"   LOCAL_TTS_ENGINE: {settings.LOCAL_TTS_ENGINE}")
    print(f"   COSYVOICE2_MODEL_PATH: {settings.COSYVOICE2_MODEL_PATH or '(自动下载)'}")
    print(f"   COSYVOICE2_DEVICE: {settings.COSYVOICE2_DEVICE}")
    print(f"   COSYVOICE2_LANGUAGE: {settings.COSYVOICE2_LANGUAGE}")
    
    if not settings.LOCAL_TTS_ENABLED:
        print("\n⚠️  警告: LOCAL_TTS_ENABLED 未启用，请在 .env 中设置 LOCAL_TTS_ENABLED=true")
        return
    
    if settings.LOCAL_TTS_ENGINE != "cosyvoice2":
        print(f"\n⚠️  警告: LOCAL_TTS_ENGINE 设置为 '{settings.LOCAL_TTS_ENGINE}'，不是 'cosyvoice2'")
        print("   请在 .env 中设置 LOCAL_TTS_ENGINE=cosyvoice2")
        return
    
    # 测试文本
    test_text = "欢迎使用 CosyVoice2 语音合成系统，这是阿里巴巴达摩院推出的高质量 TTS 模型。"
    
    print(f"\n📝 测试文本: {test_text}")
    print("\n🔄 开始合成...")
    
    try:
        output_path = await voice_service.synthesize_local_cosyvoice2(
            text=test_text,
            voice=None
        )
        
        print(f"\n✅ 合成成功!")
        print(f"   输出文件: {output_path}")
        
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            print(f"   文件大小: {file_size / 1024:.2f} KB")
            print(f"\n🎵 可以播放音频文件: {output_path}")
        else:
            print("   ⚠️  警告: 输出文件不存在")
            
    except Exception as e:
        print(f"\n❌ 合成失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_cosyvoice2())

