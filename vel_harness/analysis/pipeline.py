"""Shared trace-analysis pipeline helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from vel_harness.analysis.trace_analysis import classify_trace_failures, summarize_reports


def extract_event_stream(trace_obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract event list from a trace object."""
    for key in ("events", "output", "metadata", "observations"):
        val = trace_obj.get(key)
        if isinstance(val, list) and (not val or isinstance(val[0], dict)):
            return val
        if isinstance(val, dict):
            nested = val.get("events")
            if isinstance(nested, list) and (not nested or isinstance(nested[0], dict)):
                return nested
    if "event_type" in trace_obj:
        return [trace_obj]
    return []


def analyze_trace_objects(traces: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze trace objects into summary + per-run reports."""
    reports = []
    for trace in traces:
        events = extract_event_stream(trace)
        if not events:
            continue
        reports.append(classify_trace_failures(events))
    summary = summarize_reports(reports)
    return {
        "summary": summary,
        "reports": [
            {
                "run_id": r.run_id,
                "session_id": r.session_id,
                "stats": r.stats,
                "findings": [
                    {
                        "category": f.category,
                        "severity": f.severity,
                        "reason": f.reason,
                        "event_refs": f.event_refs,
                    }
                    for f in r.findings
                ],
            }
            for r in reports
        ],
    }

