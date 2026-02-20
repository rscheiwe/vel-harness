#!/usr/bin/env python3
"""
Run a real VelHarness call and export tracing events to JSON.

Usage:
  PYTHONPATH=/Users/richard.s/vel-harness:/Users/richard.s/vel \
  .venv311/bin/python examples/export_trace_run.py \
    --out tmp/real_traces.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

from vel_harness import VelHarness


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real harness call and export trace JSON")
    parser.add_argument("--out", default="tmp/real_traces.json", help="Output trace file path")
    parser.add_argument("--session-id", default="real-trace-session", help="Session id for the run")
    parser.add_argument(
        "--prompt",
        default=(
            "Read README.md with tools and provide a 3-bullet summary of the project. "
            "Use read_file, and do not call python or execute tools."
        ),
        help="Prompt to run with the harness",
    )
    parser.add_argument(
        "--stream-log",
        default="",
        help="Optional NDJSON file path to log raw run_stream events line-by-line",
    )
    parser.add_argument(
        "--sandbox",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable execute/execute_python tools via sandbox (default: false)",
    )
    return parser.parse_args()


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
        sandbox=args.sandbox,
        planning=True,
        skill_dirs=["examples/skills"],
    )

    text_parts: List[str] = []
    fallback_text = ""
    stream_fp = None
    if args.stream_log:
        stream_path = Path(args.stream_log)
        stream_path.parent.mkdir(parents=True, exist_ok=True)
        stream_fp = stream_path.open("w")

    try:
        async for event in harness.run_stream(args.prompt, session_id=args.session_id):
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

    result_text = "".join(text_parts).strip() or fallback_text

    state = harness.get_state()
    tracing_state: Dict[str, Any] = state.get("middlewares", {}).get("tracing", {})
    events: List[Dict[str, Any]] = tracing_state.get("events", [])

    payload = {
        "traces": [
            {
                "session_id": args.session_id,
                "result": result_text,
                "events": events,
            }
        ]
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"Wrote real trace export: {out_path}")
    if args.stream_log:
        print(f"Wrote stream log: {args.stream_log}")
    print(f"Events captured: {len(events)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
