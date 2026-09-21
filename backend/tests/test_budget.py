from __future__ import annotations

import pytest

from app.budget.tracker import BudgetExceededError, BudgetTracker, estimate_cost_usd


def test_estimate_cost_uses_known_model_price():
    cost = estimate_cost_usd("qwen-plus", input_tokens=1000, output_tokens=1000)
    assert cost == pytest.approx(0.0008 + 0.002)


def test_estimate_cost_falls_back_to_default_price_for_unknown_model():
    known = estimate_cost_usd("qwen-plus", 1000, 1000)
    unknown = estimate_cost_usd("some-model-nobody-heard-of", 1000, 1000)
    assert unknown > 0
    assert unknown != known


@pytest.mark.asyncio
async def test_fresh_user_has_zero_cost_and_is_not_exceeded(tmp_path):
    tracker = BudgetTracker(db_path=str(tmp_path / "budget.sqlite3"), max_cost_usd_per_user=1.0)
    status = await tracker.current_status(user_id=1)
    assert status.cost_usd == 0
    assert status.tokens == 0
    assert status.exceeded is False
    await tracker.ensure_within_budget(user_id=1)  # 不应该抛异常


@pytest.mark.asyncio
async def test_record_usage_accumulates_and_is_visible_in_status(tmp_path):
    tracker = BudgetTracker(db_path=str(tmp_path / "budget.sqlite3"), max_cost_usd_per_user=1.0)

    cost1 = await tracker.record_usage(
        user_id=1, thread_id="t1", model="qwen-plus", input_tokens=1000, output_tokens=500, latency_ms=100
    )
    cost2 = await tracker.record_usage(
        user_id=1, thread_id="t2", model="qwen-plus", input_tokens=1000, output_tokens=500, latency_ms=200
    )

    status = await tracker.current_status(user_id=1)
    assert status.cost_usd == pytest.approx(cost1 + cost2)
    assert status.tokens == 3000  # 两轮 (1000+500) 加起来


@pytest.mark.asyncio
async def test_usage_is_isolated_per_user(tmp_path):
    tracker = BudgetTracker(db_path=str(tmp_path / "budget.sqlite3"), max_cost_usd_per_user=1.0)

    await tracker.record_usage(
        user_id=1, thread_id="t1", model="qwen-plus", input_tokens=1000, output_tokens=1000, latency_ms=100
    )

    user1_status = await tracker.current_status(user_id=1)
    user2_status = await tracker.current_status(user_id=2)
    assert user1_status.cost_usd > 0
    assert user2_status.cost_usd == 0


@pytest.mark.asyncio
async def test_exceeding_budget_raises(tmp_path):
    tracker = BudgetTracker(db_path=str(tmp_path / "budget.sqlite3"), max_cost_usd_per_user=0.001)

    await tracker.record_usage(
        user_id=1, thread_id="t1", model="qwen-max", input_tokens=100_000, output_tokens=100_000, latency_ms=100
    )

    with pytest.raises(BudgetExceededError):
        await tracker.ensure_within_budget(user_id=1)
