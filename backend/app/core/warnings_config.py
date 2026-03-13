"""抑制第三方库的已知警告（jieba、huggingface_hub），不影响功能。"""
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="jieba._compat")
warnings.filterwarnings("ignore", category=FutureWarning, module="huggingface_hub.file_download")
warnings.filterwarnings("ignore", message=".*resume_download is deprecated.*")

