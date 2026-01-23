"""
会话管理服务
用于管理多轮对话的上下文信息
"""
import uuid
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# 内存存储会话上下文（生产环境建议使用Redis）
_session_contexts: Dict[str, Dict] = {}

class SessionService:
    """会话管理服务"""
    
    def __init__(self):
        self.max_history = 10  # 最多保留10轮对话历史
        self.session_timeout = timedelta(hours=2)  # 会话超时时间
    
    def create_session(self, character_id: Optional[int] = None) -> str:
        """创建新会话"""
        session_id = str(uuid.uuid4())
        _session_contexts[session_id] = {
            "character_id": character_id,
            "messages": [],
            "created_at": datetime.now(),
            "last_active": datetime.now()
        }
        logger.info(f"Created session: {session_id}")
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """获取会话信息"""
        if session_id not in _session_contexts:
            return None
        
        session = _session_contexts[session_id]
        
        # 检查会话是否超时
        if datetime.now() - session["last_active"] > self.session_timeout:
            del _session_contexts[session_id]
            return None
        
        session["last_active"] = datetime.now()
        return session
    
    def add_message(self, session_id: str, role: str, content: str):
        """添加消息到会话历史"""
        if session_id not in _session_contexts:
            return
        
        session = _session_contexts[session_id]
        session["messages"].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now()
        })
        
        # 限制历史消息数量
        if len(session["messages"]) > self.max_history * 2:  # 每轮对话包含user和assistant两条消息
            session["messages"] = session["messages"][-self.max_history * 2:]
        
        session["last_active"] = datetime.now()
    
    def get_conversation_history(self, session_id: str) -> List[Dict[str, str]]:
        """获取对话历史（用于LLM上下文）"""
        session = self.get_session(session_id)
        if not session:
            return []
        
        # 转换为LLM需要的格式
        history = []
        for msg in session["messages"]:
            history.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        return history
    
    def clear_session(self, session_id: str):
        """清除会话"""
        if session_id in _session_contexts:
            del _session_contexts[session_id]
            logger.info(f"Cleared session: {session_id}")
    
    def cleanup_expired_sessions(self):
        """清理过期会话"""
        now = datetime.now()
        expired_sessions = [
            sid for sid, session in _session_contexts.items()
            if now - session["last_active"] > self.session_timeout
        ]
        
        for sid in expired_sessions:
            del _session_contexts[sid]
        
        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")

# 全局会话服务实例
session_service = SessionService()

