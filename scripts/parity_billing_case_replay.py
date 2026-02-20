#!/usr/bin/env python3
"""Behavioral parity replay for billing-support in vel-harness.

Goal: approximate how Codex-style execution behaves by enforcing observable
runtime contracts in one realistic case replay.

Assertions:
- billing-support, code-truth, datastore skills are activated
- relevant billing files are read
- code-truth command is executed
- datastore command is executed
- final response includes structured sections
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
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
    "CaseNumber": "PARITY-ACC-FROZEN-001",
    "Subject": "Account frozen after payment declined, campaign paused",
    "Description": (
        "Client reports campaigns stopped. They saw payment declined and now account appears frozen. "
        "They need to resume delivery quickly."
    ),
    "Type__c": "Billing",
    "Ctegory__c": "Account Frozen",
    "Cause__c": "Payment Declined",
    "Sub_cause__c": "Card Issue",
    "Priority": "High",
    "Status": "New",
    "Origin": "Email",
}

REQUIRED_READ_BASENAMES = {
    "SKILL.md",
    "CONCEPTS.md",
    "frozen-account.md",
}


def _tool_input(event: dict[str, Any]) -> dict[str, Any]:
    v = event.get("input")
    if isinstance(v, dict):
        return v
    return {}


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


async def main() -> None:
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
You are running a real-world billing-support replay test.

Case payload (JSON):
{json.dumps(CASE_PAYLOAD, indent=2)}

Mandatory execution contract:
1) activate_skill("billing-support")
2) activate_skill("code-truth")
3) activate_skill("datastore")
4) read_file these exact files before reasoning:
   - {TABOOLA_ROOT}/plugins/1st-level-support/skills/billing-support/SKILL.md
   - {TABOOLA_ROOT}/plugins/1st-level-support/skills/billing-support/CONCEPTS.md
   - {TABOOLA_ROOT}/plugins/1st-level-support/skills/billing-support/recipes/frozen-account.md
5) execute code-truth discovery command:
   CODE_TRUTH_ROOT={TABOOLA_ROOT}/plugins/code-truth "$CODE_TRUTH_ROOT/scripts/query-index.sh" "billing payment declined frozen"
6) execute datastore query-attempt command (if it fails, include full error):
   PYTHONPATH={TABOOLA_ROOT}/plugins/datastore/lib python -c "from datastore import vertica_query; r=vertica_query('SELECT 1 AS ok'); print(r.to_pandas().to_string(index=False))"
7) provide final answer with EXACT sections:
   - Decision Path
   - Evidence
   - Proposed Resolution
   - Confidence
   - Missing Evidence / Next Actions

Do not skip tools. If any command fails, continue and report the failure.
""".strip()

    activated: list[str] = []
    read_paths: list[str] = []
    executed_commands: list[str] = []
    tool_events: list[dict[str, Any]] = []
    final_text = ""

    async for event in harness.run_stream(prompt, session_id="parity-billing-replay"):
        et = event.get("type")
        if et == "tool-input-available":
            tool_name = str(event.get("toolName") or "")
            inp = _tool_input(event)
            tool_events.append({"tool": tool_name, "input": inp})

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

    activated_set = {a.lower() for a in activated}
    read_basenames = {Path(p).name for p in read_paths}
    command_blob = "\n".join(executed_commands).lower()

    checks = {
        "activated_billing_support": "billing-support" in activated_set,
        "activated_code_truth": "code-truth" in activated_set,
        "activated_datastore": "datastore" in activated_set,
        "read_required_billing_files": REQUIRED_READ_BASENAMES.issubset(read_basenames),
        "ran_code_truth": ("query-index.sh" in command_blob) or ("code_truth_root" in command_blob),
        "ran_datastore": ("vertica_query" in command_blob) or ("verify-datastore.sh" in command_blob),
        "output_has_decision_path": bool(re.search(r"(?im)^\s*[-#* ]*decision path\b", final_text)),
        "output_has_evidence": bool(re.search(r"(?im)^\s*[-#* ]*evidence\b", final_text)),
        "output_has_proposed_resolution": bool(re.search(r"(?im)^\s*[-#* ]*proposed resolution\b", final_text)),
        "output_has_confidence": bool(re.search(r"(?im)^\s*[-#* ]*confidence\b", final_text)),
        "output_has_missing_evidence_next_actions": bool(
            re.search(r"(?im)^\s*[-#* ]*missing evidence\s*/\s*next actions\b", final_text)
        ),
    }

    passed = all(checks.values())

    report = {
        "passed": passed,
        "checks": checks,
        "activated": activated,
        "read_paths": read_paths,
        "executed_commands": executed_commands,
        "tool_event_count": len(tool_events),
        "final_preview": final_text[:2000],
    }

    print(json.dumps(report, indent=2))

    if not passed:
        raise SystemExit(2)


if __name__ == "__main__":
    asyncio.run(main())
