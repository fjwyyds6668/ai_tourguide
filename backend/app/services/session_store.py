"""
会话存储抽象：内存 / Redis 可选。
配置 REDIS_URL 时使用 Redis，多进程与重启后会话不丢失；未配置则使用内存。
"""
import json
import uuid
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _serialize_session(data: Dict) -> str:
    """将会话 dict 转为 JSON，datetime 转为 isoformat。"""
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
    """从 JSON 恢复会话，isoformat 转回 datetime。"""
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
    """内存会话存储（默认）。"""

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


class RedisSessionStore:
    """Redis 会话存储（配置 REDIS_URL 时使用）。"""

    def __init__(self, redis_url: str, default_ttl_seconds: int = 7200):
        self._redis_url = redis_url
        self._default_ttl = default_ttl_seconds
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import redis
            except ImportError:
                raise ImportError("请安装 redis: pip install redis")
            try:
                self._client = redis.from_url(
                    self._redis_url,
                    decode_responses=True,
                )
            except Exception as e:
                logger.error("Redis connection failed: %s", e)
                raise
        return self._client

    def _key(self, session_id: str) -> str:
        return f"session:{session_id}"

    def set(self, session_id: str, data: Dict, ttl_seconds: int = 0) -> None:
        ttl = ttl_seconds or self._default_ttl
        raw = _serialize_session(data)
        client = self._get_client()
        key = self._key(session_id)
        client.setex(key, ttl, raw)

    def get(self, session_id: str) -> Optional[Dict]:
        try:
            client = self._get_client()
            raw = client.get(self._key(session_id))
        except Exception as e:
            logger.warning("Redis get failed: %s", e)
            return None
        if not raw:
            return None
        return _deserialize_session(raw)

    def delete(self, session_id: str) -> None:
        try:
            self._get_client().delete(self._key(session_id))
        except Exception as e:
            logger.warning("Redis delete failed: %s", e)

    def list_session_ids(self) -> List[str]:
        try:
            client = self._get_client()
            keys = client.keys("session:*")
            return [k.replace("session:", "", 1) for k in keys]
        except Exception as e:
            logger.warning("Redis keys failed: %s", e)
            return []


def make_session_store(redis_url: Optional[str], session_timeout_hours: int = 2):
    """根据配置返回内存或 Redis 存储。未配置或 redis 未安装时使用内存。"""
    if not redis_url or not redis_url.strip():
        return MemorySessionStore()
    try:
        import redis  # noqa: F401
    except ImportError:
        logger.warning(
            "REDIS_URL 已配置但未安装 redis 包，会话将使用内存存储。安装: pip install redis"
        )
        return MemorySessionStore()
    ttl = max(3600, int(session_timeout_hours * 3600))
    return RedisSessionStore(redis_url.strip(), default_ttl_seconds=ttl)
