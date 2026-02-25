"""Hardening gate evaluation and default-flip readiness helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

from vel_harness.analysis.pipeline import extract_event_stream, normalize_event_schema


@dataclass
class GateThresholds:
    """Thresholds for hardening gate decisions."""

    min_event_reduction_pct: float = 50.0
    min_repeat_reduction_pct: float = 60.0
    required_consecutive_passes: int = 2


def evaluate_hardening_gates(
    baseline_traces: Sequence[Dict[str, Any]],
    candidate_traces: Sequence[Dict[str, Any]],
    thresholds: GateThresholds | None = None,
) -> Dict[str, Any]:
    """Evaluate hardening acceptance gates from baseline/candidate traces."""
    t = thresholds or GateThresholds()
    b_metrics = _aggregate_metrics(baseline_traces)
    c_metrics = _aggregate_metrics(candidate_traces)

    event_reduction_pct = _percent_reduction(
        b_metrics["events_per_run"],
        c_metrics["events_per_run"],
    )
    repeat_reduction_pct = _percent_reduction(
        b_metrics["repeated_identical_commands_per_run"],
        c_metrics["repeated_identical_commands_per_run"],
    )
    quality_delta = c_metrics["failures_per_run"] - b_metrics["failures_per_run"]

    checks = {
        "quality_parity": {
            "passed": quality_delta <= 0.0,
            "baseline_failures_per_run": round(b_metrics["failures_per_run"], 3),
            "candidate_failures_per_run": round(c_metrics["failures_per_run"], 3),
            "delta": round(quality_delta, 3),
        },
        "event_reduction": {
            "passed": event_reduction_pct >= t.min_event_reduction_pct,
            "baseline_events_per_run": round(b_metrics["events_per_run"], 3),
            "candidate_events_per_run": round(c_metrics["events_per_run"], 3),
            "reduction_pct": round(event_reduction_pct, 2),
            "target_pct": t.min_event_reduction_pct,
        },
        "repeat_reduction": {
            "passed": repeat_reduction_pct >= t.min_repeat_reduction_pct,
            "baseline_repeats_per_run": round(
                b_metrics["repeated_identical_commands_per_run"], 3
            ),
            "candidate_repeats_per_run": round(
                c_metrics["repeated_identical_commands_per_run"], 3
            ),
            "reduction_pct": round(repeat_reduction_pct, 2),
            "target_pct": t.min_repeat_reduction_pct,
        },
    }
    all_passed = all(c["passed"] for c in checks.values())
    return {
        "passed": all_passed,
        "checks": checks,
        "baseline_metrics": b_metrics,
        "candidate_metrics": c_metrics,
        "thresholds": {
            "min_event_reduction_pct": t.min_event_reduction_pct,
            "min_repeat_reduction_pct": t.min_repeat_reduction_pct,
            "required_consecutive_passes": t.required_consecutive_passes,
        },
    }


def update_default_flip_readiness(
    history_path: str,
    gate_result: Dict[str, Any],
    required_consecutive_passes: int = 2,
) -> Dict[str, Any]:
    """Update gate history and compute default-flip readiness."""
    path = Path(history_path)
    if path.exists():
        try:
            history = _coerce_runs_dict(path.read_text())
        except Exception:
            history = {"runs": []}
    else:
        history = {"runs": []}

    runs = history.setdefault("runs", [])
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "passed": bool(gate_result.get("passed", False)),
        "checks": gate_result.get("checks", {}),
    }
    runs.append(entry)

    streak = 0
    for run in reversed(runs):
        if run.get("passed"):
            streak += 1
        else:
            break
    ready = streak >= required_consecutive_passes
    out = {
        "required_consecutive_passes": required_consecutive_passes,
        "current_consecutive_passes": streak,
        "ready_to_flip_defaults": ready,
        "history_entries": len(runs),
        "latest": entry,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_to_json({"runs": runs}))
    return out


def _aggregate_metrics(traces: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    run_count = 0
    total_events = 0
    total_failures = 0
    total_repeats = 0
    telemetry_modes: Dict[str, int] = {}

    for trace in traces:
        raw_events = extract_event_stream(trace)
        if not raw_events:
            continue
        events = normalize_event_schema(raw_events)
        run_count += 1
        # Event reduction gate should measure emitted telemetry volume directly.
        total_events += len(raw_events)
        total_failures += sum(1 for e in events if e.get("event_type") == "tool-failure")
        total_repeats += _repeated_identical_command_count(events)
        mode = _telemetry_mode(raw_events)
        telemetry_modes[mode] = telemetry_modes.get(mode, 0) + 1

    divisor = max(1, run_count)
    return {
        "runs": run_count,
        "events_per_run": total_events / divisor,
        "failures_per_run": total_failures / divisor,
        "repeated_identical_commands_per_run": total_repeats / divisor,
        "telemetry_modes": telemetry_modes,
    }


def _telemetry_mode(events: Sequence[Dict[str, Any]]) -> str:
    for event in events:
        data = event.get("data", {})
        if isinstance(data, dict) and data.get("telemetry_mode"):
            return str(data.get("telemetry_mode"))
    return "unknown"


def _tool_signature(event: Dict[str, Any]) -> str:
    data = event.get("data", {})
    if not isinstance(data, dict):
        return ""
    tool_name = str(data.get("tool_name", ""))
    tool_input = data.get("tool_input", {})
    if not isinstance(tool_input, dict):
        tool_input = {}
    cmd = str(tool_input.get("command") or tool_input.get("cmd") or "")
    if cmd:
        return f"{tool_name}:{cmd.strip().lower()}"
    return ""


def _repeated_identical_command_count(events: Sequence[Dict[str, Any]]) -> int:
    repeats = 0
    last_sig = ""
    streak = 0
    for event in events:
        if event.get("event_type") != "tool-start":
            continue
        sig = _tool_signature(event)
        if not sig:
            continue
        if sig == last_sig:
            streak += 1
            if streak >= 2:
                repeats += 1
        else:
            last_sig = sig
            streak = 0
    return repeats


def _percent_reduction(baseline: float, candidate: float) -> float:
    if baseline <= 0:
        return 100.0 if candidate <= 0 else 0.0
    return max(0.0, ((baseline - candidate) / baseline) * 100.0)


def _coerce_runs_dict(raw: str) -> Dict[str, Any]:
    import json

    data = json.loads(raw)
    if not isinstance(data, dict):
        return {"runs": []}
    runs = data.get("runs")
    if not isinstance(runs, list):
        data["runs"] = []
    return data


def _to_json(data: Dict[str, Any]) -> str:
    import json

    return json.dumps(data, indent=2, sort_keys=True)
