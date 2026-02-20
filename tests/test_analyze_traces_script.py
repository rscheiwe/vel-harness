"""Tests for scripts/analyze_traces.py."""

from scripts.analyze_traces import run_analysis
from vel_harness.analysis import extract_event_stream


def test_extract_event_stream_prefers_events() -> None:
    trace = {"events": [{"event_type": "run-start", "seq": 1}]}
    events = extract_event_stream(trace)
    assert len(events) == 1
    assert events[0]["event_type"] == "run-start"


def test_run_analysis_emits_summary() -> None:
    traces = [
        {
            "events": [
                {"seq": 1, "event_type": "run-start", "run_id": "r1", "session_id": "s1", "data": {}},
                {
                    "seq": 2,
                    "event_type": "tool-success",
                    "run_id": "r1",
                    "session_id": "s1",
                    "data": {"tool_name": "write_file", "tool_input": {"path": "x.py"}},
                },
                {"seq": 3, "event_type": "run-end", "run_id": "r1", "session_id": "s1", "data": {}},
            ]
        }
    ]
    out = run_analysis(traces)
    assert "summary" in out
    assert out["summary"]["runs_analyzed"] == 1
    assert "reports" in out
