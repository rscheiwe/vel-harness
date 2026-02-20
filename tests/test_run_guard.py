"""Tests for RunGuard middleware."""

from vel_harness.middleware.run_guard import RunGuardConfig, RunGuardMiddleware


def test_run_guard_blocks_total_budget() -> None:
    mw = RunGuardMiddleware(
        RunGuardConfig(
            enabled=True,
            max_tool_calls_total=1,
            max_tool_calls_per_tool={},
        )
    )
    sid = "s"
    mw.start(sid)
    ok, _ = mw.allow_tool_call(sid, "read_file", {"path": "a"})
    assert ok is True
    mw.on_tool_start(sid, "read_file", {"path": "a"})
    mw.on_tool_success(sid, "read_file", {"path": "a"})

    ok, reason = mw.allow_tool_call(sid, "read_file", {"path": "b"})
    assert ok is False
    assert "budget exceeded" in reason


def test_run_guard_blocks_identical_repeats() -> None:
    mw = RunGuardMiddleware(
        RunGuardConfig(
            enabled=True,
            max_tool_calls_total=20,
            max_tool_calls_per_tool={},
            max_same_tool_input_repeats=2,
        )
    )
    sid = "s2"
    mw.start(sid)

    for _ in range(2):
        ok, _ = mw.allow_tool_call(sid, "grep", {"pattern": "x"})
        assert ok is True
        mw.on_tool_start(sid, "grep", {"pattern": "x"})
        mw.on_tool_success(sid, "grep", {"pattern": "x"})

    ok, reason = mw.allow_tool_call(sid, "grep", {"pattern": "x"})
    assert ok is False
    assert "repeated identical calls" in reason


def test_run_guard_forces_followup_without_verification() -> None:
    mw = RunGuardMiddleware(
        RunGuardConfig(
            enabled=True,
            max_tool_calls_total=20,
            max_tool_calls_per_tool={},
            require_verification_before_done=True,
            verification_tool_names=["execute"],
        )
    )
    sid = "s3"
    mw.start(sid)
    needed, reason = mw.should_force_followup(
        session_id=sid,
        user_message="Implement parser",
        response="Done. Implemented parser and finished.",
    )
    assert needed is True
    assert "No verification" in reason

    # Now provide verification evidence
    ok, _ = mw.allow_tool_call(sid, "execute", {"cmd": "pytest -q"})
    assert ok is True
    mw.on_tool_start(sid, "execute", {"cmd": "pytest -q"})
    mw.on_tool_success(sid, "execute", {"cmd": "pytest -q"})
    needed2, _ = mw.should_force_followup(
        session_id=sid,
        user_message="Implement parser",
        response="Done. Implemented parser and finished.",
    )
    assert needed2 is False

