#!/usr/bin/env python3
"""
Reproducible harness experiment wrapper.

Captures:
- exact harness config
- prompt snapshot + hash
- middleware inventory
- model config
- optional trace analysis
- optional baseline comparison
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from vel_harness import VelHarness
from vel_harness.analysis import (
    analyze_trace_objects,
    compare_analysis_payloads,
    build_harness_snapshot,
    write_experiment_bundle,
)
from scripts.analyze_traces import load_traces_from_json, fetch_langfuse_traces


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run reproducible harness experiment snapshot")
    parser.add_argument("--name", default="experiment", help="Experiment name")
    parser.add_argument("--output-dir", default=".experiments", help="Base output directory")
    parser.add_argument("--provider", default="anthropic", help="Model provider")
    parser.add_argument("--model", default="claude-sonnet-4-5-20250929", help="Model name")
    parser.add_argument("--working-directory", default="", help="Harness working directory")
    parser.add_argument("--trace-input", default="", help="Optional trace JSON input for analysis")
    parser.add_argument("--langfuse", action="store_true", help="Use Langfuse instead of --trace-input")
    parser.add_argument("--limit", type=int, default=100, help="Trace limit when using Langfuse")
    parser.add_argument(
        "--baseline-analysis",
        default="",
        help="Optional baseline analysis JSON for comparison",
    )
    return parser.parse_args()


def _load_optional_analysis(args: argparse.Namespace) -> Dict[str, Any] | None:
    traces: List[Dict[str, Any]] = []
    if args.langfuse:
        traces = fetch_langfuse_traces(args.limit)
    elif args.trace_input:
        traces = load_traces_from_json(args.trace_input)
    if not traces:
        return None
    return analyze_trace_objects(traces[: args.limit])


def main() -> int:
    args = parse_args()
    model_cfg = {"provider": args.provider, "model": args.model}
    harness = VelHarness(
        model=model_cfg,
        working_directory=args.working_directory or None,
        sandbox=False,
    )

    snapshot = build_harness_snapshot(harness)
    prompt_text = harness.deep_agent.get_system_prompt()
    analysis_payload = _load_optional_analysis(args)

    comparison_payload = None
    if args.baseline_analysis and analysis_payload is not None:
        baseline = json.loads(Path(args.baseline_analysis).read_text())
        comparison_payload = compare_analysis_payloads(baseline, analysis_payload)

    out_dir = write_experiment_bundle(
        output_dir=args.output_dir,
        name=args.name,
        snapshot=snapshot,
        prompt_text=prompt_text,
        analysis_payload=analysis_payload,
        comparison_payload=comparison_payload,
    )
    print(f"Wrote experiment bundle: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

