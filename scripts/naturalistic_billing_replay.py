#!/usr/bin/env python3
"""Naturalistic billing replay (non-forced).

Purpose:
- Test real-world behavior with minimal instruction forcing.
- Observe whether the agent *chooses* to use billing-support, code-truth,
  datastore, relevant files, and evidence-based reasoning.

Exit code is always 0 unless runtime errors occur; this is an observational eval.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from vel_harness import VelHarness

HARNESS_ROOT = Path("/Users/richard.s/vel-harness")
TABOOLA_ROOT = Path("/Users/richard.s/taboola-sales-skills")

SKILL_DIRS = [
    TABOOLA_ROOT / "plugins/1st-level-support/skills/billing-support",
    TABOOLA_ROOT / "plugins/code-truth/skills/code-truth",
    TABOOLA_ROOT / "plugins/datastore/skills/datastore",
]

CASE_PAYLOAD = {
    "CaseNumber": "NATURAL-ACC-FROZEN-001",
    "Subject": "Account frozen after payment declined, campaign paused",
    "Description": (
        "Client reports campaigns stopped. They saw payment declined and now account appears frozen. "
        "They need to resume delivery quickly and want to know exact next steps."
    ),
    "Type__c": "Billing",
    "Ctegory__c": "Account Frozen",
    "Cause__c": "Payment Declined",
    "Sub_cause__c": "Card Issue",
    "Priority": "High",
    "Status": "New",
    "Origin": "Email",
}


def _tool_input(event: dict[str, Any]) -> dict[str, Any]:
    v = event.get("input")
    return v if isinstance(v, dict) else {}


def _extract_path(inp: dict[str, Any]) -> str:
    for k in ("path", "file", "filepath"):
        if k in inp:
            return str(inp.get(k) or "")
    return ""


def _extract_command(inp: dict[str, Any]) -> str:
    for k in ("command", "cmd", "code"):
        if k in inp:
            return str(inp.get(k) or "")
    return ""


def _score(checks: dict[str, bool]) -> tuple[int, str]:
    # Weighted realism score out of 100
    weights = {
        "used_any_skill_activation": 10,
        "used_billing_support": 20,
        "read_billing_docs": 15,
        "used_code_truth": 15,
        "used_datastore": 20,
        "included_evidence_language": 10,
        "included_next_actions": 10,
    }
    total = sum(weights.values())
    got = sum(weights[k] for k, ok in checks.items() if ok and k in weights)
    pct = round((got / total) * 100)
    if pct >= 80:
        label = "strong"
    elif pct >= 55:
        label = "partial"
    else:
        label = "weak"
    return pct, label


async def main() -> None:
    parser = argparse.ArgumentParser(description="Naturalistic billing behavior replay")
    parser.add_argument("--session-id", default="naturalistic-billing-replay")
    parser.add_argument("--save-report", default="", help="Optional path to write JSON report")
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

    prompt = f"""
You are a first-level support billing engineer.

Investigate and propose the best resolution for this real case payload:
{json.dumps(CASE_PAYLOAD, indent=2)}

Use whatever tools and skills you think are necessary.
Your answer should include:
1) diagnosis
2) evidence used
3) proposed resolution steps
4) confidence
5) escalation or next actions if needed
""".strip()

    activated: list[str] = []
    read_paths: list[str] = []
    executed_commands: list[str] = []
    final_text = ""
    tool_events = 0

    async for event in harness.run_stream(prompt, session_id=args.session_id):
        et = event.get("type")
        if et == "tool-input-available":
            tool_events += 1
            tool_name = str(event.get("toolName") or "")
            inp = _tool_input(event)

            if tool_name == "activate_skill":
                name = str(inp.get("name") or "").strip()
                if name:
                    activated.append(name)

            if tool_name == "read_file":
                p = _extract_path(inp)
                if p:
                    read_paths.append(p)

            if tool_name in {"execute", "bash", "execute_python"}:
                c = _extract_command(inp)
                if c:
                    executed_commands.append(c)

        elif et == "text-delta":
            final_text += str(event.get("delta") or "")

    activated_l = [a.lower() for a in activated]
    read_blob = "\n".join(read_paths).lower()
    cmd_blob = "\n".join(executed_commands).lower()
    text_l = final_text.lower()

    checks = {
        "used_any_skill_activation": len(activated) > 0,
        "used_billing_support": any("billing-support" in a for a in activated_l),
        "read_billing_docs": (
            "billing-support/skill.md" in read_blob
            or "billing-support/concepts.md" in read_blob
            or "billing-support/recipes/frozen-account.md" in read_blob
        ),
        "used_code_truth": (
            any("code-truth" in a for a in activated_l)
            or "query-index.sh" in cmd_blob
            or "index-status.sh" in cmd_blob
        ),
        "used_datastore": (
            any("datastore" in a for a in activated_l)
            or "verify-datastore.sh" in cmd_blob
            or "vertica_query(" in cmd_blob
        ),
        "included_evidence_language": any(k in text_l for k in ["evidence", "validated", "verified", "query"]),
        "included_next_actions": any(k in text_l for k in ["next", "escalat", "follow-up", "action"]),
    }

    score, label = _score(checks)

    report = {
        "mode": "naturalistic",
        "score": score,
        "label": label,
        "checks": checks,
        "activated_skills": activated,
        "read_paths": read_paths,
        "executed_commands": executed_commands,
        "tool_event_count": tool_events,
        "final_preview": final_text[:3000],
    }

    print(json.dumps(report, indent=2))

    if args.save_report:
        out = Path(args.save_report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"\nSaved report: {out}")


if __name__ == "__main__":
    asyncio.run(main())
