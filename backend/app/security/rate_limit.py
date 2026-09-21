"""按用户的令牌桶限流。

这是进程内的简单实现——多 worker 部署下每个进程有自己的桶，不是全局精确
限流，这一点如实写在 `docs/ENGINEERING_NOTES.md` 里，不假装是生产级分布式限流。
"""

from __future__ import annotations

import time

from fastapi import Depends, HTTPException, Request, status

from app.auth.dependencies import get_current_user
from app.db.models import User


class TokenBucket:
    def __init__(self, capacity: int, refill_per_second: float) -> None:
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()

    def try_consume(self, amount: float = 1.0) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
        self.last_refill = now
        if self.tokens < amount:
            return False
        self.tokens -= amount
        return True


class RateLimiter:
    def __init__(self, capacity: int = 10, refill_per_second: float = 10 / 60) -> None:
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self._buckets: dict[int, TokenBucket] = {}

    def _bucket_for(self, user_id: int) -> TokenBucket:
        bucket = self._buckets.get(user_id)
        if bucket is None:
            bucket = TokenBucket(self.capacity, self.refill_per_second)
            self._buckets[user_id] = bucket
        return bucket

    def check(self, user_id: int) -> None:
        if not self._bucket_for(user_id).try_consume():
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="请求太频繁，请稍后再试")


async def rate_limited_user(request: Request, user: User = Depends(get_current_user)) -> User:
    """挂在 app.state 上的那个 `RateLimiter` 实例，按用户维度限流。"""
    request.app.state.rate_limiter.check(user.id)
    return user
