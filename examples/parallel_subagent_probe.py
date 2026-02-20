#!/usr/bin/env python3
"""
Probe real subagent parallelism and export trace + timing evidence.

This runs a parent harness call that uses `spawn_parallel`/`wait_all_subagents`
and asks each spawned subagent to call a custom `wait_seconds` tool.
The script then computes interval overlap and max concurrency.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv

from vel_harness import VelHarness
from vel_harness.subagents.spawner import SubagentResult


async def wait_seconds(seconds: int = 3, label: str = "") -> Dict[str, Any]:
    """Simple delay tool to create measurable runtime."""
    seconds = max(1, min(int(seconds), 30))
    started_at = datetime.utcnow().isoformat()
    await asyncio.sleep(seconds)
    ended_at = datetime.utcnow().isoformat()
    return {
        "label": label,
        "slept_seconds": seconds,
        "started_at": started_at,
        "ended_at": ended_at,
    }


def _overlap(a: Tuple[datetime, datetime], b: Tuple[datetime, datetime]) -> bool:
    return max(a[0], b[0]) < min(a[1], b[1])


def _max_concurrency(intervals: List[Tuple[datetime, datetime]]) -> int:
    points: List[Tuple[datetime, int]] = []
    for start, end in intervals:
        points.append((start, 1))
        points.append((end, -1))
    points.sort(key=lambda x: (x[0], -x[1]))
    current = 0
    max_seen = 0
    for _, delta in points:
        current += delta
        if current > max_seen:
            max_seen = current
    return max_seen


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Probe subagent parallel execution")
    p.add_argument("--out", default="tmp/parallel_probe.json", help="Output JSON path")
    p.add_argument("--subagents", type=int, default=3, help="Number of subagents")
    p.add_argument("--sleep-seconds", type=int, default=4, help="Delay each subagent should run")
    p.add_argument("--session-id", default="parallel-probe", help="Session id")
    p.add_argument(
        "--stream-log",
        default="",
        help="Optional NDJSON file path to log raw run_stream events line-by-line",
    )
    return p.parse_args()


def _serialize_event(event: Any) -> Any:
    if isinstance(event, dict):
        return event
    if hasattr(event, "__dict__"):
        return {
            k: v
            for k, v in vars(event).items()
            if isinstance(v, (str, int, float, bool, dict, list)) or v is None
        }
    return {"repr": str(event)}


async def main() -> int:
    load_dotenv()
    args = parse_args()

    harness = VelHarness(
        model={"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
        tools=[wait_seconds],
        sandbox=False,
        planning=True,
    )

    tasks = [
        (
            f"Subtask {i+1}: call wait_seconds(seconds={args.sleep_seconds}, label='S{i+1}') "
            "exactly once, then return only 'S{n} done'."
        ).replace("{n}", str(i + 1))
        for i in range(args.subagents)
    ]

    prompt = (
        "You must test parallel subagents.\n"
        "1) Call spawn_parallel with these tasks exactly:\n"
        f"{json.dumps(tasks)}\n"
        "2) Immediately call wait_all_subagents.\n"
        "3) Return a concise summary of completion statuses.\n"
    )

    text_parts: List[str] = []
    fallback_text = ""
    stream_fp = None
    if args.stream_log:
        stream_path = Path(args.stream_log)
        stream_path.parent.mkdir(parents=True, exist_ok=True)
        stream_fp = stream_path.open("w")

    try:
        async for event in harness.run_stream(prompt, session_id=args.session_id):
            if stream_fp is not None:
                line = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "event": _serialize_event(event),
                }
                stream_fp.write(json.dumps(line) + "\n")
                stream_fp.flush()

            if isinstance(event, dict) and event.get("type") == "text-delta":
                text_parts.append(event.get("delta", ""))
            elif hasattr(event, "content"):
                fallback_text = str(getattr(event, "content"))
            elif isinstance(event, dict) and "content" in event:
                fallback_text = str(event.get("content"))
    finally:
        if stream_fp is not None:
            stream_fp.close()

    response_text = "".join(text_parts).strip() or fallback_text

    tracing_state = harness.get_state().get("middlewares", {}).get("tracing", {})
    events = tracing_state.get("events", [])

    spawner_results: List[SubagentResult] = []
    if harness.deep_agent.subagents is not None:
        spawner_results = harness.deep_agent.subagents.spawner.results

    intervals: List[Tuple[datetime, datetime]] = []
    subagent_timings: List[Dict[str, Any]] = []
    for res in spawner_results:
        if res.started_at and res.completed_at:
            intervals.append((res.started_at, res.completed_at))
        subagent_timings.append(
            {
                "id": res.id,
                "task": res.task,
                "status": res.status.value,
                "started_at": res.started_at.isoformat() if res.started_at else None,
                "completed_at": res.completed_at.isoformat() if res.completed_at else None,
                "duration_seconds": res.duration_seconds,
                "error": res.error,
            }
        )

    overlap_pairs = 0
    for i in range(len(intervals)):
        for j in range(i + 1, len(intervals)):
            if _overlap(intervals[i], intervals[j]):
                overlap_pairs += 1

    report = {
        "subagent_count": len(spawner_results),
        "max_concurrency": _max_concurrency(intervals) if intervals else 0,
        "overlap_pairs": overlap_pairs,
        "parallel_evidence": overlap_pairs > 0,
    }

    payload = {
        "prompt": prompt,
        "response": response_text,
        "trace_events": events,
        "subagent_timings": subagent_timings,
        "parallel_report": report,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    print(f"Wrote parallel probe: {out}")
    if args.stream_log:
        print(f"Wrote stream log: {args.stream_log}")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
