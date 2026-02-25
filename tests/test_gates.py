"""Tests for hardening gate evaluation."""

from pathlib import Path

from vel_harness.analysis.gates import (
    GateThresholds,
    evaluate_hardening_gates,
    update_default_flip_readiness,
)


def _trace(events):
    return {"events": events}


def test_evaluate_hardening_gates_passes_when_candidate_improves() -> None:
    baseline = [
        _trace(
            [
                {"seq": 1, "event_type": "run-start", "run_id": "b1", "session_id": "s", "data": {"telemetry_mode": "debug"}},
                {"seq": 2, "event_type": "tool-start", "run_id": "b1", "session_id": "s", "data": {"tool_name": "execute", "tool_input": {"command": "pytest -q"}}},
                {"seq": 3, "event_type": "tool-start", "run_id": "b1", "session_id": "s", "data": {"tool_name": "execute", "tool_input": {"command": "pytest -q"}}},
                {"seq": 4, "event_type": "tool-failure", "run_id": "b1", "session_id": "s", "data": {"tool_name": "execute", "tool_input": {"command": "pytest -q"}, "error": "boom"}},
                {"seq": 5, "event_type": "run-end", "run_id": "b1", "session_id": "s", "data": {}},
            ]
        )
    ]
    candidate = [
        _trace(
            [
                {"seq": 1, "event_type": "run-start", "run_id": "c1", "session_id": "s", "data": {"telemetry_mode": "standard"}},
                {"seq": 2, "event_type": "tool-start", "run_id": "c1", "session_id": "s", "data": {"tool_name": "execute", "tool_input": {"command": "pytest -q"}}},
                {"seq": 3, "event_type": "run-end", "run_id": "c1", "session_id": "s", "data": {}},
            ]
        )
    ]
    result = evaluate_hardening_gates(
        baseline_traces=baseline,
        candidate_traces=candidate,
        thresholds=GateThresholds(min_event_reduction_pct=40.0, min_repeat_reduction_pct=50.0),
    )
    assert result["passed"] is True
    assert result["checks"]["quality_parity"]["passed"] is True
    assert result["checks"]["event_reduction"]["passed"] is True
    assert result["checks"]["repeat_reduction"]["passed"] is True


def test_update_default_flip_readiness_tracks_consecutive_passes(tmp_path: Path) -> None:
    history = tmp_path / "history.json"
    pass_result = {"passed": True, "checks": {"x": {"passed": True}}}
    out1 = update_default_flip_readiness(str(history), pass_result, required_consecutive_passes=2)
    assert out1["ready_to_flip_defaults"] is False
    out2 = update_default_flip_readiness(str(history), pass_result, required_consecutive_passes=2)
    assert out2["ready_to_flip_defaults"] is True
    assert out2["current_consecutive_passes"] == 2
