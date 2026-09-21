from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 锚定到仓库根目录的 .env，不依赖进程启动时的当前工作目录——
# `cd backend && uvicorn app.main:app` 和直接在仓库根目录起是两个不同的 cwd，
# 用相对路径 ".env" 会导致后一种情况悄悄读不到文件、静默退回默认值
# （这个 bug 是真的在用真实 Key 测试时踩到的：MOCK_MODE=false 写进了 .env，
# 但因为 cwd 是 backend/，Settings 没找到那个文件，还是跑的 mock 模型）。
_REPO_ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT_ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )

    mock_mode: bool = True

    dashscope_api_key: str = ""
    qwen_model: str = "qwen-plus"

    openweather_api_key: str = ""

    map_mcp_url: str = "http://localhost:8811/mcp"
    map_mcp_api_key: str = ""

    jwt_secret: str = "change-me-to-a-random-string-at-least-32-bytes-long"
    jwt_expire_minutes: int = 60 * 24
    jwt_algorithm: str = "HS256"

    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    checkpoint_db_path: str = "./data/checkpoints.sqlite3"
    idempotency_db_path: str = "./data/idempotency.sqlite3"
    trace_db_path: str = "./data/trace.sqlite3"
    budget_db_path: str = "./data/budget.sqlite3"
    bad_case_db_path: str = "./data/bad_cases.sqlite3"

    # 每个用户累计花费超过这个数（美元）就拒绝继续调用模型，防止失控消耗。
    # 价格表是近似值，不是阿里云的实时计费 API，用来做数量级预算控制。
    budget_max_cost_usd_per_user: float = 1.0

    # trace_spans 表每次模型/工具调用都落一条，没有清理会无限增长；
    # 进程启动时清一次超过这个天数的旧 span，见 main.py 的 lifespan。
    trace_retention_days: float = 30

    cors_allowed_origins: str = "http://localhost:5173"

    rate_limit_capacity: int = 10
    rate_limit_refill_per_minute: float = 10.0

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
