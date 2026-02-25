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
        events = normalize_event_schema(extract_event_stream(trace))
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


def normalize_event_schema(events: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize mixed trace schemas into legacy-compatible events.

    New compact schemas (e.g. tool_call_summary) are expanded to classic
    tool-start/tool-success/tool-failure events so existing analysis logic
    remains stable.
    """
    normalized: List[Dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        et = str(event.get("event_type", ""))
        if et != "tool_call_summary":
            normalized.append(event)
            continue

        data = event.get("data", {}) if isinstance(event.get("data"), dict) else {}
        tool_name = str(data.get("tool_name", ""))
        tool_input = data.get("tool_input_preview", {})
        if not isinstance(tool_input, dict):
            tool_input = {}
        base = {
            "run_id": event.get("run_id", ""),
            "session_id": event.get("session_id", ""),
        }
        seq = int(event.get("seq", 0))
        normalized.append(
            {
                **base,
                "seq": seq,
                "event_type": "tool-start",
                "data": {"tool_name": tool_name, "tool_input": tool_input},
            }
        )
        if str(data.get("status", "")) == "failure":
            normalized.append(
                {
                    **base,
                    "seq": seq,
                    "event_type": "tool-failure",
                    "data": {
                        "tool_name": tool_name,
                        "tool_input": tool_input,
                        "error": data.get("error", ""),
                        "error_type": data.get("error_type", ""),
                        "duration_ms": data.get("duration_ms", 0),
                    },
                }
            )
        else:
            normalized.append(
                {
                    **base,
                    "seq": seq,
                    "event_type": "tool-success",
                    "data": {
                        "tool_name": tool_name,
                        "tool_input": tool_input,
                        "duration_ms": data.get("duration_ms", 0),
                        "tool_output_preview": data.get("tool_output_preview", ""),
                    },
                }
            )
    return normalized
