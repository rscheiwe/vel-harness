#!/usr/bin/env python3
"""
Outer-loop experiment cycle:
1) analyze baseline traces
2) analyze candidate traces
3) compare regression/uplift
4) emit JSON + Markdown report
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from vel_harness.analysis import (
    GateThresholds,
    analyze_trace_objects,
    compare_analysis_payloads,
    evaluate_hardening_gates,
    fetch_langfuse_traces,
    normalize_trace_object,
    update_default_flip_readiness,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run baseline/candidate experiment comparison cycle")
    parser.add_argument("--baseline", default="", help="Baseline trace JSON file")
    parser.add_argument("--candidate", default="", help="Candidate trace JSON file")
    parser.add_argument("--langfuse-baseline", action="store_true", help="Fetch baseline traces from Langfuse")
    parser.add_argument("--langfuse-candidate", action="store_true", help="Fetch candidate traces from Langfuse")
    parser.add_argument("--limit", type=int, default=100, help="Trace limit per side")
    parser.add_argument("--out-json", default="experiment_cycle.json", help="Output JSON report path")
    parser.add_argument("--out-md", default="experiment_cycle.md", help="Output markdown report path")
    parser.add_argument("--out-gates", default="", help="Optional output path for gate evaluation JSON")
    parser.add_argument(
        "--gate-history",
        default=".experiments/hardening_gate_history.json",
        help="Path to persistent gate history used for default-flip readiness",
    )
    parser.add_argument(
        "--required-consecutive-gate-passes",
        type=int,
        default=2,
        help="Consecutive passing runs required before default flip",
    )
    parser.add_argument(
        "--min-event-reduction-pct",
        type=float,
        default=50.0,
        help="Gate threshold: minimum event reduction percent",
    )
    parser.add_argument(
        "--min-repeat-reduction-pct",
        type=float,
        default=60.0,
        help="Gate threshold: minimum repeated-command reduction percent",
    )
    return parser.parse_args()


def _load_traces(path: str) -> List[Dict[str, Any]]:
    raw = json.loads(Path(path).read_text())
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict) and isinstance(raw.get("traces"), list):
        return [r for r in raw["traces"] if isinstance(r, dict)]
    raise ValueError(f"Unsupported trace format: {path}")


def _collect_traces(file_path: str, from_langfuse: bool, limit: int) -> List[Dict[str, Any]]:
    if from_langfuse:
        return [normalize_trace_object(t) for t in fetch_langfuse_traces(limit=limit)]
    if not file_path:
        raise ValueError("Provide input file when Langfuse flag is not set")
    return _load_traces(file_path)[:limit]


def _markdown_report(
    baseline_summary: Dict[str, Any],
    candidate_summary: Dict[str, Any],
    comparison: Dict[str, Any],
    gates: Dict[str, Any] | None = None,
    readiness: Dict[str, Any] | None = None,
) -> str:
    lines = [
        "# Harness Experiment Cycle Report",
        "",
        "## Verdict",
        f"- **{comparison.get('verdict', 'unknown')}**",
        "",
        "## Totals",
        f"- Baseline failures: {comparison.get('baseline_total_failures', 0)}",
        f"- Candidate failures: {comparison.get('candidate_total_failures', 0)}",
        f"- Delta: {comparison.get('total_failure_delta', 0)}",
        "",
        "## Top Regressions",
    ]
    regressions = comparison.get("top_regressions", [])
    if regressions:
        for item in regressions:
            lines.append(f"- {item.get('category')}: +{item.get('delta')}")
    else:
        lines.append("- none")

    lines.extend(["", "## Top Improvements"])
    improvements = comparison.get("top_improvements", [])
    if improvements:
        for item in improvements:
            lines.append(f"- {item.get('category')}: {item.get('delta')}")
    else:
        lines.append("- none")

    lines.extend(["", "## Candidate Recommendations"])
    for rec in candidate_summary.get("recommendations", []):
        lines.append(f"- {rec.get('category')}: {rec.get('action')}")

    behavior = comparison.get("behavior_delta", {}) or {}
    if behavior:
        lines.extend(["", "## Behavior Deltas"])
        labels = {
            "avg_behavior_score": "Behavior score",
            "todo_compliance_rate": "Todo compliance rate",
            "parallel_capture_rate": "Parallel opportunity capture rate",
            "verification_compliance_rate": "Verification compliance rate",
            "followup_reverify_rate": "Followup re-verify rate",
        }
        for key, label in labels.items():
            row = behavior.get(key, {})
            b = row.get("baseline", 0.0)
            c = row.get("candidate", 0.0)
            d = row.get("delta", 0.0)
            lines.append(f"- {label}: {b} -> {c} ({d:+})")

    if gates:
        lines.extend(["", "## Hardening Gates"])
        lines.append(f"- Passed: {gates.get('passed', False)}")
        checks = gates.get("checks", {}) or {}
        for key in ("quality_parity", "event_reduction", "repeat_reduction"):
            row = checks.get(key, {})
            lines.append(f"- {key}: {row.get('passed', False)}")

    if readiness:
        lines.extend(["", "## Default Flip Readiness"])
        lines.append(f"- Ready to flip defaults: {readiness.get('ready_to_flip_defaults', False)}")
        lines.append(
            f"- Consecutive gate passes: {readiness.get('current_consecutive_passes', 0)}"
            f"/{readiness.get('required_consecutive_passes', 2)}"
        )

    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    baseline_traces = _collect_traces(args.baseline, args.langfuse_baseline, args.limit)
    candidate_traces = _collect_traces(args.candidate, args.langfuse_candidate, args.limit)

    baseline_payload = analyze_trace_objects(baseline_traces)
    candidate_payload = analyze_trace_objects(candidate_traces)
    comparison = compare_analysis_payloads(baseline_payload, candidate_payload)
    thresholds = GateThresholds(
        min_event_reduction_pct=args.min_event_reduction_pct,
        min_repeat_reduction_pct=args.min_repeat_reduction_pct,
        required_consecutive_passes=args.required_consecutive_gate_passes,
    )
    gates = evaluate_hardening_gates(
        baseline_traces=baseline_traces,
        candidate_traces=candidate_traces,
        thresholds=thresholds,
    )
    readiness = update_default_flip_readiness(
        history_path=args.gate_history,
        gate_result=gates,
        required_consecutive_passes=args.required_consecutive_gate_passes,
    )

    payload = {
        "baseline": baseline_payload,
        "candidate": candidate_payload,
        "comparison": comparison,
        "gates": gates,
        "default_flip_readiness": readiness,
    }
    Path(args.out_json).write_text(json.dumps(payload, indent=2, sort_keys=True))
    Path(args.out_md).write_text(
        _markdown_report(
            baseline_summary=baseline_payload.get("summary", {}),
            candidate_summary=candidate_payload.get("summary", {}),
            comparison=comparison,
            gates=gates,
            readiness=readiness,
        )
    )
    if args.out_gates:
        Path(args.out_gates).write_text(json.dumps({"gates": gates, "default_flip_readiness": readiness}, indent=2, sort_keys=True))
        print(f"Wrote {args.out_gates}")
    print(f"Wrote {args.out_json}")
    print(f"Wrote {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
