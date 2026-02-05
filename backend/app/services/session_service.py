"""
会话管理服务
用于管理多轮对话的上下文信息。
配置 REDIS_URL 时使用 Redis 持久化，多进程/重启不丢；未配置则使用内存。
"""
import uuid
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from app.core.config import settings
from app.services.session_store import make_session_store, MemorySessionStore

logger = logging.getLogger(__name__)

# 根据 REDIS_URL 选择存储：有则 Redis，无则内存
_session_timeout_hours = 2
_store = make_session_store(
    getattr(settings, "REDIS_URL", None),
    session_timeout_hours=_session_timeout_hours,
)
logger.info(
    "会话存储: %s",
    "redis" if not isinstance(_store, MemorySessionStore) else "memory",
)


class SessionService:
    """会话管理服务（委托给内存或 Redis 存储）"""

    def __init__(self):
        self.max_history = 10  # 最多保留10轮对话历史
        self.session_timeout = timedelta(hours=_session_timeout_hours)
        self._store = _store
        self._is_memory = isinstance(_store, MemorySessionStore)

    def create_session(self, character_id: Optional[int] = None) -> str:
        """创建新会话"""
        session_id = str(uuid.uuid4())
        data = {
            "character_id": character_id,
            "messages": [],
            "created_at": datetime.now(),
            "last_active": datetime.now(),
        }
        self._store.set(session_id, data, ttl_seconds=int(self.session_timeout.total_seconds()))
        logger.info("Created session: %s (store=%s)", session_id, "redis" if not self._is_memory else "memory")
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict]:
        """获取会话信息；若超时则删除并返回 None。"""
        data = self._store.get(session_id)
        if not data:
            return None

        last = data.get("last_active")
        if isinstance(last, str):
            try:
                last = datetime.fromisoformat(last.replace("Z", "+00:00"))
            except Exception:
                last = datetime.now()
        if last and datetime.now() - last > self.session_timeout:
            self._store.delete(session_id)
            return None

        data["last_active"] = datetime.now()
        # Redis 下刷新 TTL，使活跃会话不过期
        self._store.set(
            session_id,
            data,
            ttl_seconds=int(self.session_timeout.total_seconds()),
        )
        return data

    def add_message(self, session_id: str, role: str, content: str):
        """添加消息到会话历史"""
        data = self._store.get(session_id)
        if not data:
            return

        data.setdefault("messages", []).append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(),
        })
        if len(data["messages"]) > self.max_history * 2:
            data["messages"] = data["messages"][-self.max_history * 2:]
        data["last_active"] = datetime.now()
        self._store.set(
            session_id,
            data,
            ttl_seconds=int(self.session_timeout.total_seconds()),
        )

    def get_conversation_history(self, session_id: str) -> List[Dict[str, str]]:
        """获取对话历史（用于 LLM 上下文）"""
        session = self.get_session(session_id)
        if not session:
            return []
        history = []
        for msg in session.get("messages", []):
            history.append({"role": msg["role"], "content": msg["content"]})
        return history

    def clear_session(self, session_id: str):
        """清除会话"""
        self._store.delete(session_id)
        logger.info("Cleared session: %s", session_id)

    def cleanup_expired_sessions(self):
        """清理过期会话（仅内存存储需要；Redis 靠 TTL 自动过期）"""
        if not self._is_memory:
            return
        now = datetime.now()
        for sid in self._store.list_session_ids():
            data = self._store.get(sid)
            if not data:
                continue
            last = data.get("last_active")
            if isinstance(last, str):
                try:
                    last = datetime.fromisoformat(last.replace("Z", "+00:00"))
                except Exception:
                    continue
            if last and now - last > self.session_timeout:
                self._store.delete(sid)
                logger.info("Cleaned up expired session: %s", sid)


# 全局会话服务实例
session_service = SessionService()
