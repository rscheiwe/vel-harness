"""Tests for experiment cycle script helpers."""

from scripts.run_experiment_cycle import _markdown_report


def test_markdown_report_contains_verdict_and_totals() -> None:
    md = _markdown_report(
        baseline_summary={"recommendations": []},
        candidate_summary={"recommendations": [{"category": "no_verification", "action": "enforce checks"}]},
        comparison={
            "verdict": "improved",
            "baseline_total_failures": 10,
            "candidate_total_failures": 6,
            "total_failure_delta": -4,
            "top_regressions": [],
            "top_improvements": [{"category": "no_verification", "delta": -4}],
            "behavior_delta": {
                "avg_behavior_score": {"baseline": 45.0, "candidate": 70.0, "delta": 25.0},
                "todo_compliance_rate": {"baseline": 50.0, "candidate": 80.0, "delta": 30.0},
                "parallel_capture_rate": {"baseline": 0.0, "candidate": 50.0, "delta": 50.0},
                "verification_compliance_rate": {"baseline": 30.0, "candidate": 90.0, "delta": 60.0},
                "followup_reverify_rate": {"baseline": 20.0, "candidate": 70.0, "delta": 50.0},
            },
        },
    )
    assert "improved" in md
    assert "Baseline failures: 10" in md
    assert "Candidate failures: 6" in md
    assert "no_verification" in md
    assert "Behavior Deltas" in md
    assert "Todo compliance rate" in md


def test_markdown_report_includes_gate_sections() -> None:
    md = _markdown_report(
        baseline_summary={"recommendations": []},
        candidate_summary={"recommendations": []},
        comparison={
            "verdict": "flat",
            "baseline_total_failures": 1,
            "candidate_total_failures": 1,
            "total_failure_delta": 0,
            "top_regressions": [],
            "top_improvements": [],
            "behavior_delta": {},
        },
        gates={
            "passed": True,
            "checks": {
                "quality_parity": {"passed": True},
                "event_reduction": {"passed": True},
                "repeat_reduction": {"passed": True},
            },
        },
        readiness={
            "ready_to_flip_defaults": True,
            "current_consecutive_passes": 2,
            "required_consecutive_passes": 2,
        },
    )
    assert "Hardening Gates" in md
    assert "Default Flip Readiness" in md
    assert "Ready to flip defaults: True" in md
