"""测试 ffmpeg 是否可用"""
import subprocess
import sys

def check_ffmpeg():
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            print("✓ ffmpeg 已安装并可用")
            print(f"版本信息（前3行）：")
            output_lines = result.stdout.decode('utf-8', errors='ignore').split('\n')[:3]
            for line in output_lines:
                print(f"  {line}")
            return True
        else:
            print("✗ ffmpeg 命令执行失败")
            return False
    except FileNotFoundError:
        print("✗ ffmpeg 未安装或不在 PATH 中")
        print("\n安装方法：")
        print("1. 下载 ffmpeg: https://www.gyan.dev/ffmpeg/builds/")
        print("2. 解压到 C:\\ffmpeg")
        print("3. 将 C:\\ffmpeg\\bin 添加到系统 PATH")
        print("4. 重启终端")
        return False
    except Exception as e:
        print(f"✗ 检查 ffmpeg 时出错: {e}")
        return False

if __name__ == "__main__":
    print("检查 ffmpeg 状态...")
    available = check_ffmpeg()
    sys.exit(0 if available else 1)
