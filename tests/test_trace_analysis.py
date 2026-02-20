"""Tests for trace taxonomy analysis."""

from vel_harness.analysis import classify_trace_failures, summarize_reports


def _events(*items):
    return list(items)


def test_classifies_no_verification_and_premature_completion() -> None:
    events = _events(
        {"seq": 1, "event_type": "run-start", "run_id": "r1", "session_id": "s1", "data": {}},
        {
            "seq": 2,
            "event_type": "tool-success",
            "run_id": "r1",
            "session_id": "s1",
            "data": {"tool_name": "write_file", "tool_input": {"path": "a.py"}},
        },
        {
            "seq": 3,
            "event_type": "verification-followup-required",
            "run_id": "r1",
            "session_id": "s1",
            "data": {"reason": "none"},
        },
        {"seq": 4, "event_type": "run-end", "run_id": "r1", "session_id": "s1", "data": {}},
    )
    report = classify_trace_failures(events)
    cats = {f.category for f in report.findings}
    assert "no_verification" in cats
    assert "premature_completion" in cats


def test_classifies_timeout_and_recovery_failure() -> None:
    events = _events(
        {"seq": 1, "event_type": "run-start", "run_id": "r2", "session_id": "s2", "data": {}},
        {
            "seq": 2,
            "event_type": "tool-failure",
            "run_id": "r2",
            "session_id": "s2",
            "data": {"tool_name": "execute", "tool_input": {"command": "pytest -q"}, "error": "timed out"},
        },
        {
            "seq": 3,
            "event_type": "tool-failure",
            "run_id": "r2",
            "session_id": "s2",
            "data": {"tool_name": "execute", "tool_input": {"command": "pytest -q"}, "error": "timeout"},
        },
        {
            "seq": 4,
            "event_type": "tool-failure",
            "run_id": "r2",
            "session_id": "s2",
            "data": {"tool_name": "execute", "tool_input": {"command": "pytest -q"}, "error": "timeout"},
        },
    )
    report = classify_trace_failures(events)
    cats = {f.category for f in report.findings}
    assert "timeout_budget_miss" in cats
    assert "recovery_failure_after_error" in cats


def test_summarize_reports_ranks_categories() -> None:
    r1 = classify_trace_failures(
        _events(
            {"seq": 1, "event_type": "tool-success", "run_id": "a", "session_id": "s", "data": {"tool_name": "write_file", "tool_input": {"path": "x"}}},
            {"seq": 2, "event_type": "verification-followup-required", "run_id": "a", "session_id": "s", "data": {}},
        )
    )
    r2 = classify_trace_failures(
        _events(
            {"seq": 1, "event_type": "tool-success", "run_id": "b", "session_id": "s", "data": {"tool_name": "write_file", "tool_input": {"path": "y"}}},
            {"seq": 2, "event_type": "verification-followup-required", "run_id": "b", "session_id": "s", "data": {}},
        )
    )
    summary = summarize_reports([r1, r2])
    assert summary["runs_analyzed"] == 2
    assert summary["failure_counts"]["no_verification"] >= 2
    assert len(summary["recommendations"]) >= 1
    assert "behavior_summary" in summary
    assert "avg_behavior_score" in summary["behavior_summary"]


def test_behavior_stats_todo_parallel_and_verification_signals() -> None:
    events = _events(
        {"seq": 1, "event_type": "run-start", "run_id": "r3", "session_id": "s3", "data": {}},
        {
            "seq": 2,
            "event_type": "tool-start",
            "run_id": "r3",
            "session_id": "s3",
            "data": {
                "tool_name": "write_todos",
                "tool_input": {"current_task": "Implement feature"},
            },
        },
        {
            "seq": 3,
            "event_type": "tool-start",
            "run_id": "r3",
            "session_id": "s3",
            "data": {
                "tool_name": "spawn_subagent",
                "tool_input": {"task": "part A"},
            },
        },
        {
            "seq": 4,
            "event_type": "tool-start",
            "run_id": "r3",
            "session_id": "s3",
            "data": {
                "tool_name": "spawn_subagent",
                "tool_input": {"task": "part B"},
            },
        },
        {
            "seq": 5,
            "event_type": "tool-start",
            "run_id": "r3",
            "session_id": "s3",
            "data": {
                "tool_name": "spawn_parallel",
                "tool_input": {"tasks": [{"task": "x"}, {"task": "y"}]},
            },
        },
        {
            "seq": 6,
            "event_type": "tool-success",
            "run_id": "r3",
            "session_id": "s3",
            "data": {
                "tool_name": "execute",
                "tool_input": {"command": "pytest -q"},
            },
        },
        {"seq": 7, "event_type": "run-end", "run_id": "r3", "session_id": "s3", "data": {}},
    )
    report = classify_trace_failures(events)
    stats = report.stats
    behavior = stats["behavior"]
    assert stats["todo_write_calls"] == 1
    assert stats["spawn_parallel_calls"] == 1
    assert stats["spawn_subagent_calls"] == 2
    assert behavior["todo"]["discipline"] == "met"
    assert behavior["parallel"]["discipline"] == "met"
    assert behavior["verification"]["discipline"] == "met"


def test_parallel_expected_when_spawn_parallel_has_multiple_tasks() -> None:
    events = _events(
        {"seq": 1, "event_type": "run-start", "run_id": "r4", "session_id": "s4", "data": {}},
        {
            "seq": 2,
            "event_type": "tool-start",
            "run_id": "r4",
            "session_id": "s4",
            "data": {
                "tool_name": "spawn_parallel",
                "tool_input": {"tasks": [{"task": "a"}, {"task": "b"}]},
            },
        },
        {"seq": 3, "event_type": "run-end", "run_id": "r4", "session_id": "s4", "data": {}},
    )
    report = classify_trace_failures(events)
    parallel = report.stats["behavior"]["parallel"]
    assert parallel["expected"] is True
    assert parallel["used"] is True
    assert parallel["discipline"] == "met"


def test_read_only_execute_commands_do_not_mark_coding_intent() -> None:
    events = _events(
        {"seq": 1, "event_type": "run-start", "run_id": "r5", "session_id": "s5", "data": {}},
        {
            "seq": 2,
            "event_type": "tool-start",
            "run_id": "r5",
            "session_id": "s5",
            "data": {"tool_name": "execute", "tool_input": {"command": "pwd"}},
        },
        {
            "seq": 3,
            "event_type": "tool-start",
            "run_id": "r5",
            "session_id": "s5",
            "data": {"tool_name": "execute", "tool_input": {"command": "cat README.md"}},
        },
        {"seq": 4, "event_type": "run-end", "run_id": "r5", "session_id": "s5", "data": {}},
    )
    report = classify_trace_failures(events)
    assert report.stats["coding_intent"] is False
    assert report.stats["behavior"]["verification"]["expected"] is False


def test_execute_pytest_marks_coding_intent() -> None:
    events = _events(
        {"seq": 1, "event_type": "run-start", "run_id": "r6", "session_id": "s6", "data": {}},
        {
            "seq": 2,
            "event_type": "tool-start",
            "run_id": "r6",
            "session_id": "s6",
            "data": {"tool_name": "execute", "tool_input": {"command": "pytest -q tests/test_x.py"}},
        },
        {"seq": 3, "event_type": "run-end", "run_id": "r6", "session_id": "s6", "data": {}},
    )
    report = classify_trace_failures(events)
    assert report.stats["coding_intent"] is True
