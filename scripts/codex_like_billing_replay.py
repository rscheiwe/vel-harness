#!/usr/bin/env python3
"""Codex-like billing replay.

Simulates: skill is already activated, user gives only a natural request.
No forced tool contract in the user prompt.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from vel_harness import VelHarness
from vel_harness.middleware.skills import SkillInjectionMode

HARNESS_ROOT = Path("/Users/richard.s/vel-harness")
TABOOLA_ROOT = Path("/Users/richard.s/taboola-sales-skills")

BILLING_SKILL_FILE = TABOOLA_ROOT / "plugins/1st-level-support/skills/billing-support/SKILL.md"
SKILL_DIRS = [
    TABOOLA_ROOT / "plugins/1st-level-support/skills/billing-support",
    TABOOLA_ROOT / "plugins/code-truth/skills/code-truth",
    TABOOLA_ROOT / "plugins/datastore/skills/datastore",
]

CASE_PAYLOAD = {
    "CaseNumber": "CODEX-LIKE-001",
    "Subject": "Account frozen after payment declined, campaign paused",
    "Description": (
        "Client says account became frozen after payment failure and asks for fastest restore path."
    ),
    "Type__c": "Billing",
    "Ctegory__c": "Account Frozen",
    "Cause__c": "Payment Declined",
    "Sub_cause__c": "Card Issue",
}


def _tool_input(event: dict[str, Any]) -> dict[str, Any]:
    v = event.get("input")
    return v if isinstance(v, dict) else {}


def _extract_command(inp: dict[str, Any]) -> str:
    for k in ("command", "cmd", "code"):
        if k in inp:
            return str(inp.get(k) or "")
    return ""


def _resolve_skill_name_by_source(harness: VelHarness, source_path: Path) -> str:
    skills_mw = harness.deep_agent.skills
    if skills_mw is None:
        return ""
    target = str(source_path.resolve())
    for skill in skills_mw.registry.skills:
        if str(Path(skill.source_path or "").resolve()) == target:
            return skill.name
    return ""


async def main() -> None:
    parser = argparse.ArgumentParser(description="Codex-like replay with pre-activated skill context")
    parser.add_argument("--session-id", default="codex-like-billing")
    parser.add_argument("--save-report", default="")
    args = parser.parse_args()

    load_dotenv(HARNESS_ROOT / ".env")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("Missing ANTHROPIC_API_KEY in env/.env")

    harness = VelHarness(
        model={"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
        skill_dirs=[str(p) for p in SKILL_DIRS],
        sandbox=True,
        planning=True,
        database=False,
        working_directory=str(TABOOLA_ROOT),
    )

    # Make skill behavior closer to Codex-style "activated context".
    if harness.deep_agent.skills is None:
        raise SystemExit("Skills middleware not enabled")

    harness.deep_agent.skills._injection_mode = SkillInjectionMode.SYSTEM_PROMPT
    billing_skill_name = _resolve_skill_name_by_source(harness, BILLING_SKILL_FILE)
    if not billing_skill_name:
        raise SystemExit(f"Failed to resolve billing skill name from {BILLING_SKILL_FILE}")

    act = harness.deep_agent.skills._activate_skill(billing_skill_name)
    if act.get("error"):
        raise SystemExit(f"Failed to activate billing skill '{billing_skill_name}': {act['error']}")

    # Natural user request only (no forced workflow text).
    prompt = (
        "Check the billing case and determine the best resolution. "
        "Use available tools only if needed.\n\n"
        f"Case:\n{json.dumps(CASE_PAYLOAD, indent=2)}"
    )

    tool_events: list[dict[str, Any]] = []
    commands: list[str] = []
    final_text = ""

    async for event in harness.run_stream(prompt, session_id=args.session_id):
        if event.get("type") == "tool-input-available":
            tool_name = str(event.get("toolName") or "")
            inp = _tool_input(event)
            tool_events.append({"tool": tool_name, "input": inp})
            if tool_name in {"execute", "bash", "execute_python"}:
                c = _extract_command(inp)
                if c:
                    commands.append(c)
        elif event.get("type") == "text-delta":
            final_text += str(event.get("delta") or "")

    report = {
        "mode": "codex_like",
        "preactivated_skill": billing_skill_name,
        "tool_event_count": len(tool_events),
        "tools_used": [e["tool"] for e in tool_events],
        "commands": commands,
        "final_preview": final_text[:3500],
    }

    print(json.dumps(report, indent=2))

    if args.save_report:
        p = Path(args.save_report)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"\nSaved report: {p}")


if __name__ == "__main__":
    asyncio.run(main())
