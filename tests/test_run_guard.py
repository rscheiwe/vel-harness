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


def test_run_guard_classifies_data_retrieval_and_blocks_excess_discovery() -> None:
    mw = RunGuardMiddleware(
        RunGuardConfig(
            enabled=True,
            max_tool_calls_total=20,
            max_tool_calls_per_tool={},
            max_discovery_rounds_by_class={"data_retrieval": 1, "general": 2},
        )
    )
    sid = "s4"
    mw.start(sid, "What is revenue this quarter by region?")
    ok, _ = mw.allow_tool_call(sid, "read_file", {"path": "README.md"})
    assert ok is True
    mw.on_tool_start(sid, "read_file", {"path": "README.md"})
    mw.on_tool_success(sid, "read_file", {"path": "README.md"})
    ok2, reason2 = mw.allow_tool_call(sid, "grep", {"pattern": "revenue"})
    assert ok2 is False
    assert "discovery budget exceeded" in reason2


def test_run_guard_blocks_repeated_identical_execute() -> None:
    mw = RunGuardMiddleware(
        RunGuardConfig(
            enabled=True,
            max_tool_calls_total=20,
            max_tool_calls_per_tool={},
            max_repeated_identical_execute=2,
        )
    )
    sid = "s5"
    mw.start(sid)
    for _ in range(2):
        ok, _ = mw.allow_tool_call(sid, "execute", {"command": "python script.py"})
        assert ok is True
        mw.on_tool_start(sid, "execute", {"command": "python script.py"})
        mw.on_tool_success(sid, "execute", {"command": "python script.py"})
    ok3, reason3 = mw.allow_tool_call(sid, "execute", {"command": "python script.py"})
    assert ok3 is False
    assert "repeated identical command calls" in reason3


def test_run_guard_requires_evidence_for_numeric_claims() -> None:
    mw = RunGuardMiddleware(
        RunGuardConfig(
            enabled=True,
            max_tool_calls_total=20,
            max_tool_calls_per_tool={},
            enforce_query_evidence_for_numeric_claims=True,
        )
    )
    sid = "s6"
    mw.start(sid, "What is revenue this month?")
    needed, reason = mw.should_force_followup(
        session_id=sid,
        user_message="What is revenue this month?",
        response="Revenue is $1,200,000.",
    )
    assert needed is True
    assert "Numeric claim detected without query evidence" in reason

    ok, _ = mw.allow_tool_call(sid, "sql_query", {"query": "select 1"})
    assert ok is True
    mw.on_tool_start(sid, "sql_query", {"query": "select 1"})
    mw.on_tool_success(sid, "sql_query", {"query": "select 1"})
    needed2, _ = mw.should_force_followup(
        session_id=sid,
        user_message="What is revenue this month?",
        response="Revenue is $1,200,000.",
    )
    assert needed2 is False


def test_discovery_budget_rejection_is_recoverable() -> None:
    mw = RunGuardMiddleware(
        RunGuardConfig(
            enabled=True,
            max_tool_calls_total=20,
            max_tool_calls_per_tool={},
            max_discovery_rounds_by_class={"data_retrieval": 1, "general": 2},
        )
    )
    sid = "s7"
    mw.start(sid, "Investigate revenue drop and confirm metrics")
    ok, _ = mw.allow_tool_call(sid, "read_file", {"path": "README.md"})
    assert ok is True
    mw.on_tool_start(sid, "read_file", {"path": "README.md"})
    mw.on_tool_success(sid, "read_file", {"path": "README.md"})

    ok2, reason2 = mw.allow_tool_call(sid, "grep", {"pattern": "revenue"})
    assert ok2 is False
    assert "discovery budget exceeded" in reason2

    # A blocked discovery call should not globally freeze the run.
    ok3, reason3 = mw.allow_tool_call(sid, "sql_query", {"query": "select 1"})
    assert ok3 is True, reason3


def test_capability_named_tool_counts_as_query_evidence() -> None:
    mw = RunGuardMiddleware(
        RunGuardConfig(
            enabled=True,
            max_tool_calls_total=20,
            max_tool_calls_per_tool={},
            enforce_query_evidence_for_numeric_claims=True,
        )
    )
    sid = "s8"
    mw.start(sid, "Check account metrics and diagnose drop")
    ok, _ = mw.allow_tool_call(sid, "metrics_query", {"account_id": "1010748"})
    assert ok is True
    mw.on_tool_start(sid, "metrics_query", {"account_id": "1010748"})
    mw.on_tool_success(sid, "metrics_query", {"account_id": "1010748"})

    needed, _ = mw.should_force_followup(
        session_id=sid,
        user_message="Check account metrics and diagnose drop",
        response="Page-views dropped 21%.",
    )
    assert needed is False


def test_data_retrieval_requires_retry_after_query_failure() -> None:
    mw = RunGuardMiddleware(
        RunGuardConfig(
            enabled=True,
            max_tool_calls_total=20,
            max_tool_calls_per_tool={},
        )
    )
    sid = "s9"
    user_msg = "Investigate revenue drop with query evidence"
    mw.start(sid, user_msg)

    # Evidence query failed.
    mw.on_tool_start(sid, "sql_query", {"query": "select * from bad_table"})
    mw.on_tool_failure(sid, "sql_query", {"query": "select * from bad_table"})

    needed, reason = mw.should_force_followup(
        session_id=sid,
        user_message=user_msg,
        response="Revenue dropped 35%.",
    )
    assert needed is True
    assert "Most recent evidence query failed" in reason

    # Successful evidence query clears retry requirement.
    mw.on_tool_start(sid, "sql_query", {"query": "select 1"})
    mw.on_tool_success(sid, "sql_query", {"query": "select 1"})
    needed2, reason2 = mw.should_force_followup(
        session_id=sid,
        user_message=user_msg,
        response="Revenue dropped 35%.",
    )
    assert needed2 is False, reason2


def test_execute_python_query_code_counts_as_evidence() -> None:
    mw = RunGuardMiddleware(
        RunGuardConfig(
            enabled=True,
            max_tool_calls_total=20,
            max_tool_calls_per_tool={},
            enforce_query_evidence_for_numeric_claims=True,
        )
    )
    sid = "s10"
    user_msg = "Investigate revenue trend with numeric evidence"
    mw.start(sid, user_msg)
    code = "from datastore import vertica_query\nprint(vertica_query('SELECT 1'))"
    mw.on_tool_start(sid, "execute_python", {"code": code})
    mw.on_tool_success(sid, "execute_python", {"code": code})

    needed, reason = mw.should_force_followup(
        session_id=sid,
        user_message=user_msg,
        response="Revenue dropped 12%.",
    )
    assert needed is False, reason
