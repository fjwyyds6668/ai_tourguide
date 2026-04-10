"""会话管理服务（多轮对话上下文，内存存储）。"""
import uuid
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from app.services.session_store import make_session_store, MemorySessionStore

logger = logging.getLogger(__name__)

_session_timeout_hours = 2
_store = make_session_store(session_timeout_hours=_session_timeout_hours)


class SessionService:
    """会话管理服务。"""

    def __init__(self):
        self.max_history = 10
        self.session_timeout = timedelta(hours=_session_timeout_hours)
        self._store = _store

    def create_session(self, character_id: Optional[int] = None) -> str:
        session_id = str(uuid.uuid4())
        data = {
            "character_id": character_id,
            "messages": [],
            "created_at": datetime.now(),
            "last_active": datetime.now(),
        }
        self._store.set(session_id, data, ttl_seconds=int(self.session_timeout.total_seconds()))
        logger.info("Created session: %s", session_id)
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict]:
        """获取会话；超时则删除并返回 None。"""
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
        self._store.set(
            session_id,
            data,
            ttl_seconds=int(self.session_timeout.total_seconds()),
        )
        return data

    def add_message(self, session_id: str, role: str, content: str):
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
        session = self.get_session(session_id)
        if not session:
            return []
        return [{"role": msg["role"], "content": msg["content"]}
                for msg in session.get("messages", [])]

    def set_spot_list(self, session_id: str, spots: list):
        """保存本次列举的景点有序列表，供后续序号指代消解使用。"""
        data = self._store.get(session_id)
        if not data:
            return
        data["last_spot_list"] = spots
        data["last_active"] = datetime.now()
        self._store.set(session_id, data, ttl_seconds=int(self.session_timeout.total_seconds()))

    def get_spot_list(self, session_id: str) -> list:
        """获取上次列举的景点有序列表。"""
        data = self._store.get(session_id)
        if not data:
            return []
        return data.get("last_spot_list") or []

    def clear_session(self, session_id: str):
        self._store.delete(session_id)
        logger.info("Cleared session: %s", session_id)

    def cleanup_expired_sessions(self):
        """清理过期会话。"""
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


session_service = SessionService()
