#!/usr/bin/env python3
"""
Compare baseline vs candidate harness experiment outputs.

Inputs can be either:
- analysis JSON from scripts/analyze_traces.py (contains `summary` + `reports`)
- raw trace JSON export (list or {"traces": [...]})
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from vel_harness.analysis import analyze_trace_objects, compare_analysis_payloads


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare baseline and candidate experiment traces")
    parser.add_argument("--baseline", required=True, help="Baseline JSON (analysis output or raw traces)")
    parser.add_argument("--candidate", required=True, help="Candidate JSON (analysis output or raw traces)")
    parser.add_argument("--output", default="", help="Optional output path")
    return parser.parse_args()


def load_json(path: str) -> Any:
    return json.loads(Path(path).read_text())


def normalize_to_analysis_payload(data: Any) -> Dict[str, Any]:
    # Already analysis output.
    if isinstance(data, dict) and "summary" in data and "reports" in data:
        return data

    # Raw traces: {"traces":[...]} or [...]
    traces: List[Dict[str, Any]]
    if isinstance(data, dict) and isinstance(data.get("traces"), list):
        traces = [t for t in data["traces"] if isinstance(t, dict)]
        return analyze_trace_objects(traces)
    if isinstance(data, list):
        traces = [t for t in data if isinstance(t, dict)]
        return analyze_trace_objects(traces)

    raise ValueError("Unsupported input format; expected analysis payload or raw trace export")


def main() -> int:
    args = parse_args()
    baseline_payload = normalize_to_analysis_payload(load_json(args.baseline))
    candidate_payload = normalize_to_analysis_payload(load_json(args.candidate))

    comparison = compare_analysis_payloads(baseline_payload, candidate_payload)
    output = {
        "comparison": comparison,
        "baseline_summary": baseline_payload.get("summary", {}),
        "candidate_summary": candidate_payload.get("summary", {}),
    }
    text = json.dumps(output, indent=2, sort_keys=True)

    if args.output:
        Path(args.output).write_text(text)
        print(f"Wrote comparison to {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

