"""把 `eval/cases.py` 的场景接进 pytest，这样 `pytest` 全绿这句话也覆盖它们，
不需要额外记住"还要单独跑一下 eval"。独立的 `python -m eval.runner` 仍然保留，
用来在面试或者演示时打印一份可读的回归报告。
"""

from __future__ import annotations

import pytest

from eval.cases import CASES
from eval.runner import run_case


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
async def test_eval_case_passes(case):
    result = await run_case(case)
    assert result.passed, "; ".join(result.failures)
