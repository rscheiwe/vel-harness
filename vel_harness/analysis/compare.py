"""Compare baseline vs candidate trace-analysis payloads."""

from __future__ import annotations

from typing import Any, Dict


def compare_analysis_payloads(baseline: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Return regression/uplift summary between two analysis payloads."""
    b_summary = baseline.get("summary", {})
    c_summary = candidate.get("summary", {})
    b_counts = b_summary.get("failure_counts", {}) or {}
    c_counts = c_summary.get("failure_counts", {}) or {}

    categories = sorted(set(b_counts) | set(c_counts))
    deltas = {
        cat: int(c_counts.get(cat, 0)) - int(b_counts.get(cat, 0))
        for cat in categories
    }
    total_baseline = sum(int(v) for v in b_counts.values())
    total_candidate = sum(int(v) for v in c_counts.values())
    total_delta = total_candidate - total_baseline
    behavior_delta = _behavior_delta(
        b_summary.get("behavior_summary", {}) or {},
        c_summary.get("behavior_summary", {}) or {},
    )

    if total_delta < 0:
        verdict = "improved"
    elif total_delta > 0:
        verdict = "regressed"
    else:
        verdict = "flat"

    regressions = sorted(
        [{"category": k, "delta": v} for k, v in deltas.items() if v > 0],
        key=lambda x: x["delta"],
        reverse=True,
    )
    improvements = sorted(
        [{"category": k, "delta": v} for k, v in deltas.items() if v < 0],
        key=lambda x: x["delta"],
    )

    return {
        "verdict": verdict,
        "baseline_runs": int(b_summary.get("runs_analyzed", 0)),
        "candidate_runs": int(c_summary.get("runs_analyzed", 0)),
        "baseline_total_failures": total_baseline,
        "candidate_total_failures": total_candidate,
        "total_failure_delta": total_delta,
        "category_deltas": deltas,
        "top_regressions": regressions[:5],
        "top_improvements": improvements[:5],
        "behavior_delta": behavior_delta,
    }


def _behavior_delta(baseline: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    def _f(d: Dict[str, Any], k: str) -> float:
        try:
            return float(d.get(k, 0.0))
        except Exception:
            return 0.0

    keys = [
        "avg_behavior_score",
        "todo_compliance_rate",
        "parallel_capture_rate",
        "verification_compliance_rate",
        "followup_reverify_rate",
    ]
    out: Dict[str, Any] = {}
    for key in keys:
        b = _f(baseline, key)
        c = _f(candidate, key)
        out[key] = {
            "baseline": round(b, 2),
            "candidate": round(c, 2),
            "delta": round(c - b, 2),
        }
    return out
