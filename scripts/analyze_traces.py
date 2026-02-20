#!/usr/bin/env python3
"""
Analyze harness traces from Langfuse or JSON export.

Usage:
  python scripts/analyze_traces.py --input traces.json
  python scripts/analyze_traces.py --langfuse --limit 50
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from vel_harness.analysis import (
    analyze_trace_objects,
    fetch_langfuse_traces as fetch_langfuse_traces_sdk,
    normalize_trace_object,
)
from vel_harness.analysis.trace_analysis import (
    TraceAnalysisReport,
    FailureFinding,
    summarize_reports,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze harness traces with failure taxonomy")
    parser.add_argument("--input", type=str, default="", help="Path to trace JSON export")
    parser.add_argument("--langfuse", action="store_true", help="Fetch traces from Langfuse SDK")
    parser.add_argument("--limit", type=int, default=100, help="Max traces to fetch/analyze")
    parser.add_argument(
        "--parallel-shards",
        type=int,
        default=1,
        help="Analyze traces in N shards concurrently and merge",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Optional output path for analysis JSON",
    )
    return parser.parse_args()


def load_traces_from_json(path: str) -> List[Dict[str, Any]]:
    raw = json.loads(Path(path).read_text())
    if isinstance(raw, dict) and "traces" in raw and isinstance(raw["traces"], list):
        return raw["traces"]
    if isinstance(raw, list):
        return raw
    raise ValueError("Unsupported trace JSON format")


def fetch_langfuse_traces(limit: int) -> List[Dict[str, Any]]:
    traces = fetch_langfuse_traces_sdk(limit=limit)
    return [normalize_trace_object(t) for t in traces]


def run_analysis(traces: List[Dict[str, Any]], parallel_shards: int = 1) -> Dict[str, Any]:
    if parallel_shards <= 1 or len(traces) <= 1:
        return analyze_trace_objects(traces)
    return asyncio.run(_run_parallel(traces, parallel_shards))


async def _run_parallel(traces: List[Dict[str, Any]], shards: int) -> Dict[str, Any]:
    shard_size = max(1, len(traces) // shards)
    chunks = [traces[i : i + shard_size] for i in range(0, len(traces), shard_size)]
    results = await asyncio.gather(*[asyncio.to_thread(analyze_trace_objects, chunk) for chunk in chunks])

    merged_reports_json: List[Dict[str, Any]] = []
    merged_reports: List[TraceAnalysisReport] = []
    for result in results:
        for rep in result.get("reports", []):
            merged_reports_json.append(rep)
            findings = [
                FailureFinding(
                    category=f.get("category", "tool_misuse_or_instability"),
                    severity=f.get("severity", "medium"),
                    reason=f.get("reason", ""),
                    event_refs=[int(x) for x in f.get("event_refs", [])],
                )
                for f in rep.get("findings", [])
                if isinstance(f, dict)
            ]
            merged_reports.append(
                TraceAnalysisReport(
                    run_id=str(rep.get("run_id", "")),
                    session_id=str(rep.get("session_id", "")),
                    findings=findings,
                    stats=rep.get("stats", {}),
                )
            )

    summary = summarize_reports(merged_reports)
    return {"summary": summary, "reports": merged_reports_json}


def main() -> int:
    args = parse_args()

    traces: List[Dict[str, Any]]
    if args.input:
        traces = load_traces_from_json(args.input)
    elif args.langfuse:
        traces = fetch_langfuse_traces(args.limit)
    else:
        raise SystemExit("Specify --input or --langfuse")

    payload = run_analysis(traces[: args.limit], parallel_shards=max(1, args.parallel_shards))
    out = json.dumps(payload, indent=2, sort_keys=True)

    if args.output:
        Path(args.output).write_text(out)
        print(f"Wrote analysis to {args.output}")
    else:
        print(out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
