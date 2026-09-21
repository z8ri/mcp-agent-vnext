"""成本与延迟预算。

候选架构（`PROJECT_DOSSIER.md` §11）横切能力那一行明确写了"成本与延迟
预算"，早先的实现漏掉了这一项——`VNEXT_STATUS.md` 里从来没有追踪过，
不是"进行中"，是彻底没做。这里补上：按用户累计 token 花费，超过预算
在真正调用模型之前就拦住；每轮延迟也记下来，方便后续设延迟 SLA。

价格表是近似值，不是阿里云的实时计费 API——这个模块要做的是"防止失控
消耗"这件事本身，不是精确对账。`ChatTongyi` 的 token 用量在
`response_metadata["token_usage"]` 里，不是 LangChain 标准的
`usage_metadata` 字段（这个是真的调用真实通义千问核实过的，不是照着
文档猜的——`usage_metadata` 在实测里是 `None`）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from app.config import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS budget_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    thread_id TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    latency_ms REAL NOT NULL,
    recorded_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_budget_usage_user ON budget_usage (user_id, recorded_at);
"""

# 每 1K token 的近似价格（美元）：(input, output)。数量级参考，不是实时价格。
_MODEL_PRICE_PER_1K_TOKENS_USD: dict[str, tuple[float, float]] = {
    "qwen-turbo": (0.0003, 0.0006),
    "qwen-plus": (0.0008, 0.002),
    "qwen-max": (0.0024, 0.0096),
}
_DEFAULT_PRICE = (0.001, 0.002)


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = _MODEL_PRICE_PER_1K_TOKENS_USD.get(model, _DEFAULT_PRICE)
    return (input_tokens / 1000) * price_in + (output_tokens / 1000) * price_out


@dataclass
class BudgetStatus:
    cost_usd: float
    tokens: int
    limit_usd: float

    @property
    def exceeded(self) -> bool:
        return self.cost_usd >= self.limit_usd


class BudgetExceededError(Exception):
    def __init__(self, status: BudgetStatus) -> None:
        self.status = status
        super().__init__(f"用户累计花费 ${status.cost_usd:.4f} 已达到预算上限 ${status.limit_usd:.4f}")


class BudgetTracker:
    def __init__(self, db_path: str | None = None, max_cost_usd_per_user: float | None = None) -> None:
        settings = get_settings()
        self._db_path = db_path or settings.budget_db_path
        self._limit = (
            max_cost_usd_per_user if max_cost_usd_per_user is not None else settings.budget_max_cost_usd_per_user
        )
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    async def current_status(self, user_id: int) -> BudgetStatus:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.executescript(_SCHEMA)
            cursor = await conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0), COALESCE(SUM(input_tokens + output_tokens), 0) "
                "FROM budget_usage WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
        cost, tokens = row
        return BudgetStatus(cost_usd=cost, tokens=int(tokens), limit_usd=self._limit)

    async def ensure_within_budget(self, user_id: int) -> None:
        status = await self.current_status(user_id)
        if status.exceeded:
            raise BudgetExceededError(status)

    async def record_usage(
        self,
        user_id: int,
        thread_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
    ) -> float:
        cost = estimate_cost_usd(model, input_tokens, output_tokens)
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.executescript(_SCHEMA)
            await conn.execute(
                """
                INSERT INTO budget_usage
                    (user_id, thread_id, model, input_tokens, output_tokens, cost_usd, latency_ms, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, thread_id, model, input_tokens, output_tokens, cost, latency_ms, time.time()),
            )
            await conn.commit()
        return cost
