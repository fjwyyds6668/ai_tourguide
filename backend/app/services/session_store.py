"""会话存储（内存）。"""
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


def _serialize_session(data: Dict) -> str:
    """将会话 dict 序列化为 JSON（datetime → isoformat）。"""
    def _enc(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: _enc(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_enc(x) for x in obj]
        return obj
    return json.dumps(_enc(data), ensure_ascii=False)


def _deserialize_session(raw: str) -> Optional[Dict]:
    """从 JSON 反序列化会话（isoformat → datetime）。"""
    try:
        data = json.loads(raw)
    except Exception as e:
        logger.warning("session deserialize failed: %s", e)
        return None

    def _dec(obj: Any) -> Any:
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if k in ("created_at", "last_active") and isinstance(v, str):
                    try:
                        out[k] = datetime.fromisoformat(v.replace("Z", "+00:00"))
                    except Exception:
                        out[k] = v
                elif k == "messages" and isinstance(v, list):
                    out[k] = []
                    for m in v:
                        msg = dict(m)
                        if isinstance(msg.get("timestamp"), str):
                            try:
                                msg["timestamp"] = datetime.fromisoformat(
                                    msg["timestamp"].replace("Z", "+00:00")
                                )
                            except Exception:
                                pass
                        out[k].append(msg)
                else:
                    out[k] = _dec(v) if isinstance(v, (dict, list)) else v
            return out
        if isinstance(obj, list):
            return [_dec(x) for x in obj]
        return obj

    return _dec(data)


class MemorySessionStore:
    """内存会话存储。"""

    def __init__(self):
        self._store: Dict[str, Dict] = {}

    def set(self, session_id: str, data: Dict, ttl_seconds: int = 0) -> None:
        self._store[session_id] = data

    def get(self, session_id: str) -> Optional[Dict]:
        return self._store.get(session_id)

    def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)

    def list_session_ids(self) -> List[str]:
        return list(self._store.keys())


def make_session_store(session_timeout_hours: int = 2) -> MemorySessionStore:
    return MemorySessionStore()
