from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.dependencies import get_db_session
from app.auth.security import create_access_token
from app.auth.service import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    authenticate_user,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class AuthRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/register", response_model=TokenResponse)
async def register(body: AuthRequest, session: AsyncSession = Depends(get_db_session)) -> TokenResponse:
    try:
        user = await register_user(session, body.email, body.password)
    except EmailAlreadyRegisteredError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已注册") from None
    return TokenResponse(access_token=create_access_token(user.email))


@router.post("/login", response_model=TokenResponse)
async def login(body: AuthRequest, session: AsyncSession = Depends(get_db_session)) -> TokenResponse:
    try:
        user = await authenticate_user(session, body.email, body.password)
    except InvalidCredentialsError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误") from None
    return TokenResponse(access_token=create_access_token(user.email))
