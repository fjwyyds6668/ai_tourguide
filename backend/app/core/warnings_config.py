"""
警告配置模块

在导入其他模块之前配置警告过滤器，避免第三方库的已知警告。
"""
import warnings

# 抑制 jieba 的 pkg_resources 弃用警告
# jieba 0.42.1 仍使用已弃用的 pkg_resources API，这是库内部问题
warnings.filterwarnings("ignore", category=UserWarning, module="jieba._compat")

# 抑制 huggingface_hub 的 resume_download 弃用警告
# huggingface_hub 0.36.0 使用已弃用的 resume_download 参数，这是库内部问题
warnings.filterwarnings("ignore", category=FutureWarning, module="huggingface_hub.file_download")
warnings.filterwarnings("ignore", message=".*resume_download is deprecated.*")

