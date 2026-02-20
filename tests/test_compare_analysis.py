"""Tests for experiment comparison helpers and script normalization."""

from vel_harness.analysis import compare_analysis_payloads
from scripts.compare_experiments import normalize_to_analysis_payload


def test_compare_analysis_payloads_improved() -> None:
    baseline = {
        "summary": {
            "runs_analyzed": 2,
            "failure_counts": {"no_verification": 4},
            "behavior_summary": {"avg_behavior_score": 40.0, "verification_compliance_rate": 25.0},
        }
    }
    candidate = {
        "summary": {
            "runs_analyzed": 2,
            "failure_counts": {"no_verification": 1},
            "behavior_summary": {"avg_behavior_score": 70.0, "verification_compliance_rate": 75.0},
        }
    }
    cmp = compare_analysis_payloads(baseline, candidate)
    assert cmp["verdict"] == "improved"
    assert cmp["total_failure_delta"] == -3
    assert cmp["behavior_delta"]["avg_behavior_score"]["delta"] == 30.0
    assert cmp["behavior_delta"]["verification_compliance_rate"]["delta"] == 50.0


def test_normalize_raw_traces_to_analysis_payload() -> None:
    raw = [
        {
            "events": [
                {"seq": 1, "event_type": "run-start", "run_id": "r", "session_id": "s", "data": {}},
                {
                    "seq": 2,
                    "event_type": "tool-success",
                    "run_id": "r",
                    "session_id": "s",
                    "data": {"tool_name": "write_file", "tool_input": {"path": "x.py"}},
                },
                {"seq": 3, "event_type": "run-end", "run_id": "r", "session_id": "s", "data": {}},
            ]
        }
    ]
    payload = normalize_to_analysis_payload(raw)
    assert "summary" in payload
    assert "reports" in payload
