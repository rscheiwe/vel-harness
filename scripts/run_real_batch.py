#!/usr/bin/env python3
"""
Run a batch of real VelHarness tasks and export traces + stream logs.

Outputs:
- traces JSON (for analyze_traces.py)
- per-run NDJSON stream logs
- batch summary JSON
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


DEFAULT_PROMPTS: List[str] = [
    "Read README.md and summarize the project in 3 bullets. Use tools.",
    "Use glob to find Python files under vel_harness/middleware and list 10 key files.",
    "Use grep to find mentions of 'time_budget' under vel_harness and summarize what it controls.",
    "Read docs/HARNESS_OPERATIONS.md and list the top 5 operational commands.",
    "Create tmp/batch_note.txt with a short note, then edit it to add a second line, then read it back.",
    "Use write_todos to create a 3-item plan for improving harness reliability, then read_todos and summarize.",
    "Find where run_subagent_workflow is defined and explain its purpose in 3 bullets.",
    "Read scripts/run_experiment_cycle.py and summarize baseline/candidate comparison behavior.",
    "List all tools you can use in this run and group them by purpose.",
    "Inspect vel_harness/middleware/tracing.py and summarize how run events are recorded.",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run real VelHarness batch and export traces")
    p.add_argument("--out", default="tmp/real_batch_traces.json", help="Output traces JSON file")
    p.add_argument(
        "--stream-dir",
        default="tmp/real_batch_stream",
        help="Directory for per-run NDJSON stream logs",
    )
    p.add_argument(
        "--summary-out",
        default="tmp/real_batch_summary.json",
        help="Output summary JSON file",
    )
    p.add_argument(
        "--prompts-file",
        default="",
        help="Optional JSON file containing a list of prompt strings",
    )
    p.add_argument("--limit", type=int, default=10, help="Max prompts to run")
    p.add_argument("--session-prefix", default="real-batch", help="Session prefix")
    p.add_argument("--per-run-timeout", type=int, default=90, help="Timeout seconds per run")
    p.add_argument("--max-turns", type=int, default=40, help="Harness max turns per run")
    p.add_argument(
        "--sandbox",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable execute/execute_python tools via sandbox (default: true)",
    )
    return p.parse_args()


def _serialize_event(event: Any) -> Dict[str, Any]:
    if isinstance(event, dict):
        return event
    if hasattr(event, "__dict__"):
        payload = {}
        for k, v in vars(event).items():
            if isinstance(v, (str, int, float, bool, dict, list)) or v is None:
                payload[k] = v
        return payload
    return {"repr": str(event)}


def _load_prompts(path: str) -> List[str]:
    if not path:
        return list(DEFAULT_PROMPTS)
    raw = json.loads(Path(path).read_text())
    if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
        raise ValueError("prompts-file must be a JSON array of strings")
    return list(raw)


async def _run_one(
    harness: VelHarness,
    prompt: str,
    session_id: str,
    stream_path: Path,
    event_offset: int,
) -> Dict[str, Any]:
    stream_path.parent.mkdir(parents=True, exist_ok=True)
    fp = stream_path.open("w")
    text_parts: List[str] = []
    fallback_text = ""
    error_text = ""
    try:
        async for event in harness.run_stream(prompt, session_id=session_id):
            line = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": _serialize_event(event),
            }
            fp.write(json.dumps(line) + "\n")
            fp.flush()

            if isinstance(event, dict) and event.get("type") == "text-delta":
                text_parts.append(event.get("delta", ""))
            elif isinstance(event, dict) and event.get("type") == "error":
                error_text = str(event.get("error", "unknown_error"))
            elif hasattr(event, "content"):
                fallback_text = str(getattr(event, "content"))
            elif isinstance(event, dict) and "content" in event:
                fallback_text = str(event.get("content"))
    finally:
        fp.close()

    state = harness.get_state()
    tracing_events = state.get("middlewares", {}).get("tracing", {}).get("events", [])
    run_events = tracing_events[event_offset:]
    result_text = "".join(text_parts).strip() or fallback_text
    status = "error" if error_text else "completed"
    return {
        "session_id": session_id,
        "prompt": prompt,
        "status": status,
        "error": error_text or None,
        "result": result_text,
        "events": run_events,
        "stream_log": str(stream_path),
    }


async def main() -> int:
    load_dotenv()
    args = parse_args()
    prompts = _load_prompts(args.prompts_file)[: max(1, args.limit)]

    harness = VelHarness(
        model={"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
        sandbox=args.sandbox,
        planning=True,
        max_turns=max(5, args.max_turns),
        skill_dirs=["examples/skills"],
    )

    traces: List[Dict[str, Any]] = []
    for idx, prompt in enumerate(prompts, start=1):
        session_id = f"{args.session_prefix}-{idx:02d}"
        stream_path = Path(args.stream_dir) / f"{idx:02d}.ndjson"
        current_events = harness.get_state().get("middlewares", {}).get("tracing", {}).get("events", [])
        event_offset = len(current_events)
        try:
            run_trace = await asyncio.wait_for(
                _run_one(
                    harness=harness,
                    prompt=prompt,
                    session_id=session_id,
                    stream_path=stream_path,
                    event_offset=event_offset,
                ),
                timeout=max(10, args.per_run_timeout),
            )
        except asyncio.TimeoutError:
            state = harness.get_state()
            tracing_events = state.get("middlewares", {}).get("tracing", {}).get("events", [])
            run_trace = {
                "session_id": session_id,
                "prompt": prompt,
                "status": "error",
                "error": f"timeout_after_{args.per_run_timeout}s",
                "result": "",
                "events": tracing_events[event_offset:],
                "stream_log": str(stream_path),
            }
        traces.append(run_trace)
        print(f"[{idx}/{len(prompts)}] {session_id}: {run_trace['status']}")

    out_payload = {"traces": traces}
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_payload, indent=2))

    summary = {
        "runs": len(traces),
        "completed": sum(1 for t in traces if t.get("status") == "completed"),
        "errors": sum(1 for t in traces if t.get("status") == "error"),
        "trace_file": str(out_path),
        "stream_dir": str(Path(args.stream_dir)),
    }
    summary_path = Path(args.summary_out)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2))

    print(f"Wrote traces: {out_path}")
    print(f"Wrote summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
