"""Failure taxonomy and behavior synthesis for harness traces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Literal, Sequence


FailureCategory = Literal[
    "no_verification",
    "tool_misuse_or_instability",
    "looping_or_doom_edits",
    "timeout_budget_miss",
    "premature_completion",
    "recovery_failure_after_error",
]


@dataclass
class FailureFinding:
    category: FailureCategory
    severity: Literal["low", "medium", "high"]
    reason: str
    event_refs: List[int] = field(default_factory=list)


@dataclass
class TraceAnalysisReport:
    run_id: str
    session_id: str
    findings: List[FailureFinding] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)


def classify_trace_failures(events: Sequence[Dict[str, Any]]) -> TraceAnalysisReport:
    """Classify a single run's trace events into failure categories."""
    run_id = _first_value(events, "run_id")
    session_id = _first_value(events, "session_id")

    report = TraceAnalysisReport(run_id=run_id, session_id=session_id)
    tool_events = [e for e in events if e.get("event_type", "").startswith("tool-")]
    tool_successes = [e for e in tool_events if e.get("event_type") == "tool-success"]
    tool_failures = [e for e in tool_events if e.get("event_type") == "tool-failure"]
    verification_events = [
        e
        for e in tool_successes
        if _has_verify_signal(e.get("data", {}).get("tool_input", {}))
    ]

    coding_intent = _has_coding_intent(events)
    todo_stats = _todo_stats(tool_events)
    parallel_stats = _parallel_stats(tool_events)
    verify_followups = [e for e in events if e.get("event_type") == "verification-followup-required"]
    verification_gate_followups = [
        e for e in verify_followups if str(e.get("data", {}).get("source", "")) == "verification"
    ]
    behavior = _behavior_assessment(
        coding_intent=coding_intent,
        tool_events=tool_events,
        verification_events=verification_events,
        verify_followups=verify_followups,
        todo_stats=todo_stats,
        parallel_stats=parallel_stats,
    )

    report.stats = {
        "event_count": len(events),
        "tool_calls": len(tool_events),
        "tool_successes": len(tool_successes),
        "tool_failures": len(tool_failures),
        "coding_intent": coding_intent,
        "verification_calls": len(verification_events),
        "verification_followups": len(verification_gate_followups),
        **todo_stats,
        **parallel_stats,
        "behavior": behavior,
    }

    # no_verification
    if coding_intent and not verification_events:
        report.findings.append(
            FailureFinding(
                category="no_verification",
                severity="high",
                reason="Coding-intent run completed without any verification command.",
                event_refs=_event_refs(events, "run-end"),
            )
        )

    # tool_misuse_or_instability
    if tool_events and (len(tool_failures) / max(1, len(tool_events))) >= 0.5:
        report.findings.append(
            FailureFinding(
                category="tool_misuse_or_instability",
                severity="medium",
                reason="Tool failure rate exceeded 50% in this run.",
                event_refs=[e.get("seq", 0) for e in tool_failures],
            )
        )

    # looping_or_doom_edits
    loop_hints = [e for e in events if e.get("event_type") == "loop-recovery-hint"]
    if loop_hints:
        report.findings.append(
            FailureFinding(
                category="looping_or_doom_edits",
                severity="high",
                reason="Loop recovery hint triggered due to repeated edits/failures.",
                event_refs=[e.get("seq", 0) for e in loop_hints],
            )
        )

    # timeout_budget_miss
    timeout_fails = [
        e
        for e in tool_failures
        if "timeout" in str(e.get("data", {}).get("error", "")).lower()
        or "timed out" in str(e.get("data", {}).get("error", "")).lower()
    ]
    if timeout_fails:
        report.findings.append(
            FailureFinding(
                category="timeout_budget_miss",
                severity="high",
                reason="Timeout-related failures occurred.",
                event_refs=[e.get("seq", 0) for e in timeout_fails],
            )
        )

    # premature_completion
    if verification_gate_followups:
        report.findings.append(
            FailureFinding(
                category="premature_completion",
                severity="medium",
                reason="Run attempted to finalize before verification pass.",
                event_refs=[e.get("seq", 0) for e in verification_gate_followups],
            )
        )

    # recovery_failure_after_error
    if _has_unrecovered_failure_burst(tool_events):
        report.findings.append(
            FailureFinding(
                category="recovery_failure_after_error",
                severity="high",
                reason="Three or more consecutive tool failures without recovery.",
                event_refs=[e.get("seq", 0) for e in tool_failures],
            )
        )

    return report


def summarize_reports(reports: Sequence[TraceAnalysisReport]) -> Dict[str, Any]:
    """Aggregate reports and produce ranked recommendations."""
    counts: Dict[str, int] = {}
    for report in reports:
        for finding in report.findings:
            counts[finding.category] = counts.get(finding.category, 0) + 1

    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    recommendations = [_recommendation_for(category, count) for category, count in ranked]

    behavior_summary = _summarize_behavior(reports)
    return {
        "runs_analyzed": len(reports),
        "failure_counts": counts,
        "ranked_failures": ranked,
        "recommendations": recommendations,
        "behavior_summary": behavior_summary,
    }


def _recommendation_for(category: str, count: int) -> Dict[str, Any]:
    mapping = {
        "no_verification": "Strengthen verification gate and enforce test command execution before final answer.",
        "tool_misuse_or_instability": "Tighten tool prompts/hooks and add retries/backoff tuning for unstable operations.",
        "looping_or_doom_edits": "Lower loop-detection thresholds and force replan after repeated file edits.",
        "timeout_budget_miss": "Adjust reasoning scheduler and add earlier time-budget pivots to verification mode.",
        "premature_completion": "Increase strictness of pre-completion checklist and stop interception.",
        "recovery_failure_after_error": "Add explicit error-recovery playbook prompts and alternate-tool fallback paths.",
    }
    return {
        "category": category,
        "count": count,
        "action": mapping.get(category, "Investigate this failure cluster and add targeted middleware controls."),
    }


def _first_value(events: Sequence[Dict[str, Any]], key: str) -> str:
    for event in events:
        value = event.get(key)
        if value:
            return str(value)
    return ""


def _event_refs(events: Sequence[Dict[str, Any]], event_type: str) -> List[int]:
    return [int(e.get("seq", 0)) for e in events if e.get("event_type") == event_type]


def _has_verify_signal(tool_input: Dict[str, Any]) -> bool:
    cmd = str(tool_input.get("command") or tool_input.get("cmd") or "").lower()
    return any(
        tok in cmd
        for tok in (
            "pytest",
            "test",
            "go test",
            "cargo test",
            "npm test",
            "pnpm test",
            "py_compile",
            "ruff check",
            "mypy",
            "make compile",
            "make smoke",
        )
    )


def _has_code_exec_signal(command: str) -> bool:
    cmd = command.lower().strip()
    if not cmd:
        return False
    # Read-only shell probes should not mark a run as coding-intent.
    read_only_prefixes = (
        "pwd",
        "ls",
        "cat ",
        "head ",
        "tail ",
        "find ",
        "grep ",
        "rg ",
        "which ",
    )
    if any(cmd.startswith(prefix) for prefix in read_only_prefixes):
        return False

    coding_tokens = (
        "pytest",
        "py_compile",
        "python -m",
        "python ",
        "make ",
        "npm ",
        "pnpm ",
        "yarn ",
        "go test",
        "cargo test",
        "ruff",
        "mypy",
        "tsc",
    )
    return any(tok in cmd for tok in coding_tokens)


def _has_coding_intent(events: Sequence[Dict[str, Any]]) -> bool:
    # Infer from file-edit activity or explicit verification-followup requirement.
    code_exts = (".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".rs", ".cpp", ".c", ".cs", ".rb", ".php", ".swift", ".kt")
    for event in events:
        et = event.get("event_type")
        if et == "verification-followup-required":
            source = str(event.get("data", {}).get("source", ""))
            if source == "verification":
                return True
            continue
        if et in {"tool-start", "tool-success", "tool-failure"}:
            name = str(event.get("data", {}).get("tool_name", ""))
            data = event.get("data", {})
            tool_input = data.get("tool_input", {}) if isinstance(data, dict) else {}
            path = str(tool_input.get("path", "")).lower() if isinstance(tool_input, dict) else ""
            if name == "execute":
                command = str(tool_input.get("command", "")) if isinstance(tool_input, dict) else ""
                if _has_code_exec_signal(command):
                    return True
            elif name == "execute_python":
                return True
            if name in {"write_file", "edit_file"} and path.endswith(code_exts):
                return True
    return False


def _has_unrecovered_failure_burst(tool_events: Sequence[Dict[str, Any]]) -> bool:
    streak = 0
    for event in tool_events:
        et = event.get("event_type")
        if et == "tool-failure":
            streak += 1
            if streak >= 3:
                return True
        elif et == "tool-success":
            streak = 0
    return False


def _tool_name(event: Dict[str, Any]) -> str:
    return str(event.get("data", {}).get("tool_name", "")).strip()


def _tool_input(event: Dict[str, Any]) -> Dict[str, Any]:
    data = event.get("data", {})
    raw = data.get("tool_input", {}) if isinstance(data, dict) else {}
    return raw if isinstance(raw, dict) else {}


def _todo_stats(tool_events: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    write_todos = 0
    read_todos = 0
    for event in tool_events:
        if event.get("event_type") != "tool-start":
            continue
        name = _tool_name(event)
        if name == "write_todos":
            write_todos += 1
        elif name == "read_todos":
            read_todos += 1
    return {
        "todo_write_calls": write_todos,
        "todo_read_calls": read_todos,
        "todo_calls_total": write_todos + read_todos,
    }


def _parallel_stats(tool_events: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    spawn_parallel_calls = 0
    parallel_tasks_total = 0
    spawn_subagent_calls = 0
    workflow_calls = 0
    for event in tool_events:
        if event.get("event_type") != "tool-start":
            continue
        name = _tool_name(event)
        inp = _tool_input(event)
        if name == "spawn_parallel":
            spawn_parallel_calls += 1
            tasks = inp.get("tasks", [])
            if isinstance(tasks, list):
                parallel_tasks_total += len(tasks)
        elif name == "spawn_subagent":
            spawn_subagent_calls += 1
        elif name == "run_subagent_workflow":
            workflow_calls += 1
    return {
        "spawn_parallel_calls": spawn_parallel_calls,
        "parallel_tasks_total": parallel_tasks_total,
        "spawn_subagent_calls": spawn_subagent_calls,
        "workflow_calls": workflow_calls,
        "subagent_calls_total": spawn_parallel_calls + spawn_subagent_calls + workflow_calls,
    }


def _behavior_assessment(
    *,
    coding_intent: bool,
    tool_events: Sequence[Dict[str, Any]],
    verification_events: Sequence[Dict[str, Any]],
    verify_followups: Sequence[Dict[str, Any]],
    todo_stats: Dict[str, int],
    parallel_stats: Dict[str, int],
) -> Dict[str, Any]:
    tool_calls = len(tool_events)
    unique_tools = len({_tool_name(e) for e in tool_events if _tool_name(e)})
    subagent_calls_total = int(parallel_stats.get("subagent_calls_total", 0))

    expected_todos = bool(
        coding_intent
        and (
            tool_calls >= 6
            or unique_tools >= 4
            or subagent_calls_total > 0
        )
    )
    todo_used = int(todo_stats.get("todo_write_calls", 0)) > 0
    if expected_todos:
        todo_discipline = "met" if todo_used else "missed"
    else:
        todo_discipline = "not_applicable"

    spawn_subagent_calls = int(parallel_stats.get("spawn_subagent_calls", 0))
    spawn_parallel_calls = int(parallel_stats.get("spawn_parallel_calls", 0))
    parallel_tasks_total = int(parallel_stats.get("parallel_tasks_total", 0))
    # Treat explicit multi-task spawn_parallel intent as a parallel opportunity,
    # in addition to the original "many sequential subagent calls" signal.
    expected_parallel = (spawn_subagent_calls >= 2) or (spawn_parallel_calls > 0 and parallel_tasks_total >= 2)
    parallel_used = spawn_parallel_calls > 0
    if expected_parallel:
        parallel_discipline = "met" if parallel_used else "missed"
    elif parallel_used:
        parallel_discipline = "used"
    else:
        parallel_discipline = "not_applicable"

    expected_verification = coding_intent
    verified = len(verification_events) > 0
    verification_discipline = (
        "met"
        if (not expected_verification or verified)
        else "missed"
    )

    followups = len(verify_followups)
    reverified_after_followup = bool(followups > 0 and verified)

    score = 100
    if expected_todos and not todo_used:
        score -= 25
    if expected_parallel and not parallel_used:
        score -= 20
    if expected_verification and not verified:
        score -= 35
    if followups > 0 and not reverified_after_followup:
        score -= 15
    score = max(0, min(100, score))

    return {
        "score": score,
        "todo": {
            "expected": expected_todos,
            "used": todo_used,
            "discipline": todo_discipline,
        },
        "parallel": {
            "expected": expected_parallel,
            "used": parallel_used,
            "discipline": parallel_discipline,
        },
        "verification": {
            "expected": expected_verification,
            "verified": verified,
            "followups": followups,
            "reverified_after_followup": reverified_after_followup,
            "discipline": verification_discipline,
        },
    }


def _summarize_behavior(reports: Sequence[TraceAnalysisReport]) -> Dict[str, Any]:
    runs = len(reports)
    if runs == 0:
        return {
            "avg_behavior_score": 0.0,
            "todo_expected_runs": 0,
            "todo_compliant_runs": 0,
            "todo_compliance_rate": 0.0,
            "parallel_opportunity_runs": 0,
            "parallel_captured_runs": 0,
            "parallel_capture_rate": 0.0,
            "verification_expected_runs": 0,
            "verification_compliant_runs": 0,
            "verification_compliance_rate": 0.0,
            "followup_runs": 0,
            "reverified_followup_runs": 0,
            "followup_reverify_rate": 0.0,
        }

    scores: List[int] = []
    todo_expected = 0
    todo_compliant = 0
    parallel_expected = 0
    parallel_captured = 0
    verify_expected = 0
    verify_compliant = 0
    followup_runs = 0
    reverified_runs = 0

    for report in reports:
        behavior = report.stats.get("behavior", {})
        if not isinstance(behavior, dict):
            continue
        score = behavior.get("score")
        if isinstance(score, int):
            scores.append(score)

        todo = behavior.get("todo", {})
        if isinstance(todo, dict) and bool(todo.get("expected")):
            todo_expected += 1
            if bool(todo.get("used")):
                todo_compliant += 1

        parallel = behavior.get("parallel", {})
        if isinstance(parallel, dict) and bool(parallel.get("expected")):
            parallel_expected += 1
            if bool(parallel.get("used")):
                parallel_captured += 1

        verify = behavior.get("verification", {})
        if isinstance(verify, dict):
            if bool(verify.get("expected")):
                verify_expected += 1
                if bool(verify.get("verified")):
                    verify_compliant += 1
            followups = int(verify.get("followups", 0) or 0)
            if followups > 0:
                followup_runs += 1
                if bool(verify.get("reverified_after_followup")):
                    reverified_runs += 1

    def _rate(n: int, d: int) -> float:
        if d <= 0:
            return 0.0
        return round((n / d) * 100.0, 2)

    avg_score = round(sum(scores) / max(1, len(scores)), 2)

    return {
        "avg_behavior_score": avg_score,
        "todo_expected_runs": todo_expected,
        "todo_compliant_runs": todo_compliant,
        "todo_compliance_rate": _rate(todo_compliant, todo_expected),
        "parallel_opportunity_runs": parallel_expected,
        "parallel_captured_runs": parallel_captured,
        "parallel_capture_rate": _rate(parallel_captured, parallel_expected),
        "verification_expected_runs": verify_expected,
        "verification_compliant_runs": verify_compliant,
        "verification_compliance_rate": _rate(verify_compliant, verify_expected),
        "followup_runs": followup_runs,
        "reverified_followup_runs": reverified_runs,
        "followup_reverify_rate": _rate(reverified_runs, followup_runs),
    }
