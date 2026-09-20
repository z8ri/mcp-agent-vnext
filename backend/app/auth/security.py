"""密码哈希 + JWT 签发/校验。

直接用 `bcrypt` 库，不经过 `passlib`——`passlib` 已经停止维护，跟新版 `bcrypt`
（去掉了 `__about__` 之类的旧属性）不兼容，会在 hash 阶段直接抛
"password cannot be longer than 72 bytes" 这种跟实际输入长度无关的假错误。
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(subject: str, *, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    minutes = expires_minutes if expires_minutes is not None else settings.jwt_expire_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": int(time.time()),
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


class TokenError(Exception):
    pass


def decode_access_token(token: str) -> str:
    """返回 token 里的 subject（这里是用户 email）；无效/过期都抛 TokenError。"""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    subject = payload.get("sub")
    if not subject:
        raise TokenError("token 缺少 sub 字段")
    return subject
