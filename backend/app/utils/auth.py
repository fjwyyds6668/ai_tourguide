"""认证工具函数"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from passlib.exc import UnknownHashError
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def _bcrypt_password_too_long(password: str) -> bool:
    # bcrypt 最大只处理 72 bytes（非 72 字符）
    try:
        return len(password.encode("utf-8")) > 72
    except Exception:
        return True

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        if _bcrypt_password_too_long(plain_password):
            return False
        return pwd_context.verify(plain_password, hashed_password)
    except UnknownHashError:
        return False

def get_password_hash(password: str) -> str:
    # bcrypt 超长会抛 ValueError，转为友好异常由上层转 HTTP 400
    if _bcrypt_password_too_long(password):
        raise ValueError("密码过长（bcrypt 限制为最多 72 bytes），请缩短后重试")
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None

