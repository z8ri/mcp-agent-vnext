from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.security import hash_password, verify_password
from app.db.models import User


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


async def register_user(session: AsyncSession, email: str, password: str) -> User:
    existing = await session.exec(select(User).where(User.email == email))
    if existing.first() is not None:
        raise EmailAlreadyRegisteredError(email)

    user = User(email=email, password_hash=hash_password(password))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User:
    result = await session.exec(select(User).where(User.email == email))
    user = result.first()
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError(email)
    return user
