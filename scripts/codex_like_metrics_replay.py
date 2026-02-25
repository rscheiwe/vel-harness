#!/usr/bin/env python3
"""Codex-like metrics replay.

Goal:
- Validate harness routing for a support + metrics task.
- Pre-activate `1st-level-support` (Codex-like loaded context).
- Let the run decide whether to activate datastore/code-truth.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
from pathlib import Path
from typing import Any, Optional, Tuple

from dotenv import load_dotenv

from vel_harness import VelHarness
from vel_harness.middleware.skills import SkillInjectionMode

HARNESS_ROOT = Path("/Users/richard.s/vel-harness")
TABOOLA_ROOT = Path("/Users/richard.s/taboola-sales-skills")

FLS_SKILL_FILE = TABOOLA_ROOT / "plugins/1st-level-support/skills/1st-level-support/SKILL.md"
DATASTORE_SKILL_FILE = TABOOLA_ROOT / "plugins/datastore/skills/datastore/SKILL.md"
CODE_TRUTH_SKILL_FILE = TABOOLA_ROOT / "plugins/code-truth/skills/code-truth/SKILL.md"

SKILL_DIRS = [
    TABOOLA_ROOT / "plugins/1st-level-support/skills/1st-level-support",
    TABOOLA_ROOT / "plugins/datastore/skills/datastore",
    TABOOLA_ROOT / "plugins/code-truth/skills/code-truth",
]

CASE_PAYLOAD = {
    "CaseNumber": "CODEX-LIKE-METRICS-001",
    "AccountId": "1010748",
    "Subject": "Account 1010748 reports page-view drop",
    "Description": (
        "Publisher reports a significant page-view drop and asks for quick diagnosis with "
        "evidence-backed metrics."
    ),
    "Type__c": "Support",
    "Category__c": "Traffic Drop",
    "Priority": "High",
}

_INVALID_DATASTORE_IMPORT_RE = re.compile(
    r"^\s*from\s+plugins\.datastore(?:\.plugin)?\s+import\s+.+$",
    flags=re.IGNORECASE | re.MULTILINE,
)
_QUERY_VERTICA_IMPORT_RE = re.compile(
    r"^\s*from\s+plugins\.datastore\s+import\s+query_vertica\s*$",
    flags=re.IGNORECASE | re.MULTILINE,
)
_QUERY_IMPORT_RE = re.compile(
    r"^\s*from\s+datastore\s+import\s+query\s*$",
    flags=re.IGNORECASE | re.MULTILINE,
)


def taboola_datastore_rewriter(
    tool_name: str,
    kwargs: dict[str, Any],
    working_dir: Optional[str],
) -> Optional[Tuple[dict[str, Any], str]]:
    """Workspace-specific execute_python rewrite for datastore calls."""
    if tool_name != "execute_python":
        return None
    code = kwargs.get("code")
    if not isinstance(code, str) or not code.strip():
        return None
    wd = str(working_dir or "")
    if "taboola-sales-skills" not in wd:
        return None

    has_invalid_plugins_import = bool(_INVALID_DATASTORE_IMPORT_RE.search(code))
    has_query_vertica_import = bool(_QUERY_VERTICA_IMPORT_RE.search(code))
    needs_bootstrap = (
        has_invalid_plugins_import
        or has_query_vertica_import
        or ("from datastore import" in code)
        or ("vertica_query(" in code)
        or ("query_vertica(" in code)
    )
    if not needs_bootstrap:
        return None

    datastore_lib = str(Path(wd) / "plugins/datastore/lib")
    user_code = _INVALID_DATASTORE_IMPORT_RE.sub("", code)
    user_code = _QUERY_VERTICA_IMPORT_RE.sub("", user_code)
    user_code = _QUERY_IMPORT_RE.sub("", user_code).lstrip()
    payload = (
        "from datastore import vertica_query\n"
        "query = vertica_query\n"
        "query_vertica = vertica_query\n\n"
        f"{user_code}"
    )
    payload_b64 = base64.b64encode(payload.encode("utf-8", errors="replace")).decode("ascii")

    rewritten = (
        "import base64\n"
        "import os\n"
        "import subprocess\n"
        "import sys\n"
        "\n"
        f"_payload_b64 = {payload_b64!r}\n"
        "_env = os.environ.copy()\n"
        f"_lib = {datastore_lib!r}\n"
        "_env['PYTHONPATH'] = _lib + (':' + _env['PYTHONPATH'] if _env.get('PYTHONPATH') else '')\n"
        "_runner = (\n"
        "    \"import base64\\n\"\n"
        "    \"import sys\\n\"\n"
        "    \"src=base64.b64decode(sys.argv[1].encode('ascii')).decode('utf-8', errors='replace')\\n\"\n"
        "    \"g={'__name__':'__main__'}\\n\"\n"
        "    \"exec(compile(src, '<vh-exec-python>', 'exec'), g, g)\\n\"\n"
        ")\n"
        "_proc = subprocess.run(\n"
        "    ['uv', 'run', 'python', '-c', _runner, _payload_b64],\n"
        f"    cwd={wd!r},\n"
        "    env=_env,\n"
        "    capture_output=True,\n"
        "    text=True,\n"
        ")\n"
        "if _proc.stdout:\n"
        "    sys.stdout.write(_proc.stdout)\n"
        "if _proc.stderr:\n"
        "    sys.stderr.write(_proc.stderr)\n"
        "raise SystemExit(_proc.returncode)\n"
    )
    out = dict(kwargs)
    out["code"] = rewritten
    return out, "taboola_datastore_rewriter: normalized execute_python datastore bootstrap"


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


def _score(checks: dict[str, bool]) -> tuple[int, str]:
    weights = {
        "preactivated_1st_level_support": 25,
        "used_datastore_skill": 25,
        "used_code_truth_skill_or_lookup": 15,
        "ran_query_command": 20,
        "included_metrics_evidence": 15,
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
    parser = argparse.ArgumentParser(
        description="Codex-like support+metrics replay with pre-activated 1st-level-support"
    )
    parser.add_argument("--session-id", default="codex-like-metrics")
    parser.add_argument("--save-report", default="")
    args = parser.parse_args()

    load_dotenv(HARNESS_ROOT / ".env")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("Missing ANTHROPIC_API_KEY in env/.env")

    harness = VelHarness(
        model={"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
        skill_dirs=[str(p) for p in SKILL_DIRS],
        tool_input_rewriters=[taboola_datastore_rewriter],
        sandbox=True,
        planning=True,
        database=False,
        working_directory=str(TABOOLA_ROOT),
    )

    skills_mw = harness.deep_agent.skills
    if skills_mw is None:
        raise SystemExit("Skills middleware not enabled")

    # Codex-like loaded context behavior.
    skills_mw._injection_mode = SkillInjectionMode.SYSTEM_PROMPT
    fls_skill_name = _resolve_skill_name_by_source(harness, FLS_SKILL_FILE)
    if not fls_skill_name:
        raise SystemExit(f"Failed to resolve 1st-level-support skill from {FLS_SKILL_FILE}")

    act = skills_mw._activate_skill(fls_skill_name)
    if act.get("error"):
        raise SystemExit(f"Failed to activate support skill '{fls_skill_name}': {act['error']}")

    datastore_skill_name = _resolve_skill_name_by_source(harness, DATASTORE_SKILL_FILE)
    code_truth_skill_name = _resolve_skill_name_by_source(harness, CODE_TRUTH_SKILL_FILE)

    prompt = (
        "Investigate this case and provide a support resolution with metric evidence. "
        "Use tools only if needed.\n\n"
        f"Case:\n{json.dumps(CASE_PAYLOAD, indent=2)}\n\n"
        "Requirements:\n"
        "1) Diagnose probable causes\n"
        "2) Include last 7-day page-view trend evidence for account 1010748\n"
        "3) If applicable, include lineage/source confidence for the metric path\n"
        "4) Provide clear next actions/escalation"
    )

    tool_events: list[dict[str, Any]] = []
    commands: list[str] = []
    activated_runtime: list[str] = []
    final_text = ""

    async for event in harness.run_stream(prompt, session_id=args.session_id):
        if event.get("type") == "tool-input-available":
            tool_name = str(event.get("toolName") or "")
            inp = _tool_input(event)
            tool_events.append({"tool": tool_name, "input": inp})
            if tool_name == "activate_skill":
                nm = str(inp.get("name") or "").strip()
                if nm:
                    activated_runtime.append(nm)
            if tool_name in {"execute", "bash", "execute_python"}:
                c = _extract_command(inp)
                if c:
                    commands.append(c)
        elif event.get("type") == "text-delta":
            final_text += str(event.get("delta") or "")

    activated_l = [a.lower() for a in activated_runtime]
    cmd_blob = "\n".join(commands).lower()
    text_l = final_text.lower()

    checks = {
        "preactivated_1st_level_support": bool(fls_skill_name),
        "used_datastore_skill": bool(
            datastore_skill_name and any(datastore_skill_name.lower() in a for a in activated_l)
        ),
        "used_code_truth_skill_or_lookup": bool(
            (code_truth_skill_name and any(code_truth_skill_name.lower() in a for a in activated_l))
            or "code-truth" in cmd_blob
        ),
        "ran_query_command": any(tok in cmd_blob for tok in ("select ", "datastore", "vertica", "mysql", "bq query")),
        "included_metrics_evidence": any(
            tok in text_l for tok in ("page-view", "page view", "trend", "7-day", "query", "evidence")
        ),
    }
    score, label = _score(checks)

    report = {
        "mode": "codex_like_metrics",
        "preactivated_skill": fls_skill_name,
        "case": CASE_PAYLOAD,
        "score": score,
        "label": label,
        "checks": checks,
        "tool_event_count": len(tool_events),
        "tools_used": [e["tool"] for e in tool_events],
        "activated_skills_runtime": activated_runtime,
        "commands": commands,
        "final_preview": final_text[:4000],
    }

    print(json.dumps(report, indent=2))

    if args.save_report:
        out = Path(args.save_report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"\nSaved report: {out}")


if __name__ == "__main__":
    asyncio.run(main())
