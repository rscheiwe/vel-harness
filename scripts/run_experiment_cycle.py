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
    analyze_trace_objects,
    compare_analysis_payloads,
    fetch_langfuse_traces,
    normalize_trace_object,
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

    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    baseline_traces = _collect_traces(args.baseline, args.langfuse_baseline, args.limit)
    candidate_traces = _collect_traces(args.candidate, args.langfuse_candidate, args.limit)

    baseline_payload = analyze_trace_objects(baseline_traces)
    candidate_payload = analyze_trace_objects(candidate_traces)
    comparison = compare_analysis_payloads(baseline_payload, candidate_payload)

    payload = {
        "baseline": baseline_payload,
        "candidate": candidate_payload,
        "comparison": comparison,
    }
    Path(args.out_json).write_text(json.dumps(payload, indent=2, sort_keys=True))
    Path(args.out_md).write_text(
        _markdown_report(
            baseline_summary=baseline_payload.get("summary", {}),
            candidate_summary=candidate_payload.get("summary", {}),
            comparison=comparison,
        )
    )
    print(f"Wrote {args.out_json}")
    print(f"Wrote {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
