"""Tests for time budget middleware."""

import time

from vel_harness.middleware.time_budget import TimeBudgetMiddleware


def test_time_budget_warns_soft_then_hard() -> None:
    mw = TimeBudgetMiddleware(enabled=True, soft_limit_seconds=1, hard_limit_seconds=2)
    sid = "s"
    mw.start(sid)
    time.sleep(1.1)
    hint1 = mw.get_runtime_hint(sid)
    assert hint1 is not None and "Soft time budget" in hint1
    # Second call should not repeat same warning.
    assert mw.get_runtime_hint(sid) is None
    time.sleep(1.0)
    hint2 = mw.get_runtime_hint(sid)
    assert hint2 is not None and "Hard time budget" in hint2


def test_time_budget_state_roundtrip() -> None:
    mw = TimeBudgetMiddleware(enabled=True, soft_limit_seconds=10, hard_limit_seconds=20)
    state = mw.get_state()
    mw2 = TimeBudgetMiddleware(enabled=False, soft_limit_seconds=1, hard_limit_seconds=2)
    mw2.load_state(state)
    loaded = mw2.get_state()
    assert loaded["soft_limit_seconds"] == 10
    assert loaded["hard_limit_seconds"] == 20

