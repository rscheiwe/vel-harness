#!/usr/bin/env python3
"""Smoke test: billing-support skill chaining with code-truth + datastore.

This script creates a minimal temporary skill set so activation names are stable,
then runs a single harness prompt that must:
1) activate billing-support, code-truth, datastore
2) run code-truth commands
3) run datastore readiness command
4) summarize outputs
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from vel_harness import VelHarness

REPO_ROOT = Path("/Users/richard.s/taboola-sales-skills")
BILLING_SKILL = REPO_ROOT / "plugins/1st-level-support/skills/billing-support/SKILL.md"
CODE_TRUTH_SKILL = REPO_ROOT / "plugins/code-truth/skills/code-truth/SKILL.md"
DATASTORE_SKILL = REPO_ROOT / "plugins/datastore/skills/datastore/SKILL.md"


def wrap_skill(out_path: Path, name: str, description: str, source: Path) -> None:
    body = source.read_text(encoding="utf-8")
    content = (
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        "enabled: true\n"
        "priority: 100\n"
        "---\n\n"
        + body
    )
    out_path.write_text(content, encoding="utf-8")


async def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("Missing ANTHROPIC_API_KEY (set in env or /Users/richard.s/vel-harness/.env)")

    with tempfile.TemporaryDirectory(prefix="vel-billing-skill-chain-") as td:
        tmp_skills = Path(td)
        wrap_skill(
            tmp_skills / "billing-support.md",
            "billing-support",
            "Billing support triage and resolution skill",
            BILLING_SKILL,
        )
        wrap_skill(
            tmp_skills / "code-truth.md",
            "code-truth",
            "Repo indexing and lineage discovery",
            CODE_TRUTH_SKILL,
        )
        wrap_skill(
            tmp_skills / "datastore.md",
            "datastore",
            "Read-only multi-DB query layer",
            DATASTORE_SKILL,
        )

        harness = VelHarness(
            model={"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
            skill_dirs=[str(tmp_skills)],
            sandbox=True,
            planning=True,
            database=False,
        )

        prompt = f"""
You must execute this exact workflow and show command outputs.

1. activate_skill(\"billing-support\")
2. activate_skill(\"code-truth\")
3. activate_skill(\"datastore\")
4. execute command:
   CODE_TRUTH_ROOT={REPO_ROOT}/plugins/code-truth \\
   \"$CODE_TRUTH_ROOT/scripts/index-status.sh\"
5. execute command:
   CODE_TRUTH_ROOT={REPO_ROOT}/plugins/code-truth \\
   \"$CODE_TRUTH_ROOT/scripts/query-index.sh\" \"billing frozen account\"
6. execute command:
   DATASTORE_ROOT={REPO_ROOT}/plugins/datastore \\
   \"$DATASTORE_ROOT/scripts/verify-datastore.sh\" --quick
7. Summarize whether chaining billing-support -> code-truth -> datastore worked.

Do not skip tools. If any command fails, include the exact error and continue.
""".strip()

        print("=== Running smoke billing chain ===")
        print(f"Temporary skills dir: {tmp_skills}")
        print()

        tool_sequence: list[str] = []
        final_text = ""

        async for event in harness.run_stream(prompt, session_id="smoke-billing-chain"):
            et = event.get("type")
            if et == "tool-input-available":
                tool_name = event.get("toolName", "unknown")
                tool_sequence.append(tool_name)
                print(f"[tool] {tool_name}")
            elif et == "text-delta":
                delta = event.get("delta", "")
                final_text += delta

        print("\n=== Tool sequence ===")
        for i, t in enumerate(tool_sequence, start=1):
            print(f"{i}. {t}")

        print("\n=== Final response ===")
        print(final_text.strip() or "(no text)")


if __name__ == "__main__":
    asyncio.run(main())
