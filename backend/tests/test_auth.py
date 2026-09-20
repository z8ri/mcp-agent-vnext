from __future__ import annotations

import pytest

from app.auth.security import TokenError, create_access_token, decode_access_token
from app.auth.service import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    authenticate_user,
    register_user,
)


@pytest.mark.asyncio
async def test_register_then_authenticate(db_session):
    user = await register_user(db_session, "a@example.com", "correct horse battery staple")
    assert user.id is not None
    assert user.password_hash != "correct horse battery staple"  # 确认真的哈希过，不是明文

    authenticated = await authenticate_user(db_session, "a@example.com", "correct horse battery staple")
    assert authenticated.id == user.id


@pytest.mark.asyncio
async def test_wrong_password_rejected(db_session):
    await register_user(db_session, "b@example.com", "right-password")
    with pytest.raises(InvalidCredentialsError):
        await authenticate_user(db_session, "b@example.com", "wrong-password")


@pytest.mark.asyncio
async def test_duplicate_email_rejected(db_session):
    await register_user(db_session, "c@example.com", "pw1")
    with pytest.raises(EmailAlreadyRegisteredError):
        await register_user(db_session, "c@example.com", "pw2")


def test_access_token_roundtrip():
    token = create_access_token("user@example.com")
    assert decode_access_token(token) == "user@example.com"


def test_expired_token_rejected():
    token = create_access_token("user@example.com", expires_minutes=-1)
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_tampered_token_rejected():
    token = create_access_token("user@example.com")
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(TokenError):
        decode_access_token(tampered)
