"""Tests for strengthening runtime behaviors."""

from dataclasses import dataclass
from typing import Any, Dict, List

import pytest

from vel_harness.config import DeepAgentConfig
from vel_harness.factory import DeepAgent
from vel_harness.middleware.local_context import LocalContextMiddleware
from vel_harness.middleware.tracing import (
    TELEMETRY_MODE_DEBUG,
    TracingMiddleware,
)
from vel_harness.middleware.verification import VerificationMiddleware


@dataclass
class _Response:
    content: str
    messages: List[Dict[str, Any]]


class _FakeAgent:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.generation_config: Dict[str, Any] = {}

    async def run(self, payload: Dict[str, Any], session_id: str | None = None) -> _Response:
        self.calls.append({"payload": payload, "session_id": session_id})
        return _Response(content="done", messages=[])

    async def run_stream(self, payload: Dict[str, Any], session_id: str | None = None):
        self.calls.append({"payload": payload, "session_id": session_id})
        yield {"type": "start-step"}
        yield {"type": "text-delta", "delta": "done"}
        yield {
            "type": "tool-input-start",
            "toolCallId": "tool-1",
            "toolName": "read_file",
        }
        yield {
            "type": "tool-input-available",
            "toolCallId": "tool-1",
            "toolName": "read_file",
            "input": {"path": "README.md"},
        }
        yield {
            "type": "tool-output-available",
            "toolCallId": "tool-1",
            "output": {"content": "ok"},
        }
        yield {"type": "finish-step"}
        yield {"type": "finish"}


@pytest.mark.asyncio
async def test_verification_followup_for_coding_task() -> None:
    cfg = DeepAgentConfig()
    fake = _FakeAgent()
    verification = VerificationMiddleware(enabled=True, strict=True, max_followups=1)
    tracing = TracingMiddleware(enabled=True, emit_langfuse=False)
    agent = DeepAgent(
        config=cfg,
        agent=fake,  # type: ignore[arg-type]
        middlewares={"verification": verification, "tracing": tracing},
        _skip_deprecation=True,
    )

    await agent.run("Implement a function to parse CSV", session_id="s1")
    # First call + forced follow-up pass because no test command was run.
    assert len(fake.calls) == 2
    followup_payload = fake.calls[-1]["payload"]
    assert "verification pass" in followup_payload["message"].lower()
    run_end_events = [e for e in tracing.events if e.event_type == "run-end"]
    assert run_end_events
    assert "final_output_preview" in run_end_events[-1].data


@pytest.mark.asyncio
async def test_run_stream_records_assistant_stream_events() -> None:
    cfg = DeepAgentConfig()
    fake = _FakeAgent()
    tracing = TracingMiddleware(enabled=True, emit_langfuse=False)
    agent = DeepAgent(
        config=cfg,
        agent=fake,  # type: ignore[arg-type]
        middlewares={"tracing": tracing},
        _skip_deprecation=True,
    )

    out = []
    async for e in agent.run_stream("Read file and summarize", session_id="s-stream"):
        out.append(e)

    assert out
    event_types = [e.event_type for e in tracing.events]
    assert "assistant_step_summary" in event_types
    assert "tool_call_summary" in event_types
    assert "assistant-finish" not in event_types


def test_stream_event_emits_generation_before_tool_call_in_step() -> None:
    tracing = TracingMiddleware(enabled=True, emit_langfuse=False)
    tracing.start_run("s-stage")
    tracing.record_stream_event("s-stage", {"type": "start-step"})
    tracing.record_stream_event("s-stage", {"type": "text-delta", "delta": "I'll read it."})
    tracing.record_stream_event(
        "s-stage",
        {"type": "tool-input-start", "toolCallId": "t1", "toolName": "read_file"},
    )
    tracing.record_stream_event(
        "s-stage",
        {
            "type": "tool-input-available",
            "toolCallId": "t1",
            "toolName": "read_file",
            "input": {"path": "README.md"},
        },
    )
    tracing.record_stream_event(
        "s-stage",
        {"type": "tool-output-available", "toolCallId": "t1", "output": {"content": "ok"}},
    )
    tracing.record_stream_event("s-stage", {"type": "finish-step"})
    tracing.record_stream_event("s-stage", {"type": "finish"})
    tracing.end_run(success=True)

    event_types = [e.event_type for e in tracing.events]
    gen_idx = event_types.index("assistant_step_summary")
    tool_idx = event_types.index("tool_call_summary")
    assert gen_idx < tool_idx


def test_stream_tool_output_nonzero_exit_is_failure_summary() -> None:
    tracing = TracingMiddleware(enabled=True, emit_langfuse=False)
    tracing.start_run("s-out-fail")
    tracing.record_stream_event("s-out-fail", {"type": "start-step"})
    tracing.record_stream_event(
        "s-out-fail",
        {"type": "tool-input-start", "toolCallId": "t1", "toolName": "execute_python"},
    )
    tracing.record_stream_event(
        "s-out-fail",
        {
            "type": "tool-input-available",
            "toolCallId": "t1",
            "toolName": "execute_python",
            "input": {"code": "print('x')"},
        },
    )
    tracing.record_stream_event(
        "s-out-fail",
        {
            "type": "tool-output-available",
            "toolCallId": "t1",
            "output": {"exit_code": 1, "success": False, "stderr": "Traceback ..."},
        },
    )
    tracing.record_stream_event("s-out-fail", {"type": "finish"})
    tracing.end_run(success=True)

    summaries = [e for e in tracing.events if e.event_type == "tool_call_summary"]
    assert summaries
    assert summaries[-1].data.get("status") == "failure"
    assert summaries[-1].data.get("error_type") == "ToolOutputFailure"


@pytest.mark.asyncio
async def test_local_context_injected_once_per_session(tmp_path) -> None:
    cfg = DeepAgentConfig()
    cfg.local_context.enabled = True
    fake = _FakeAgent()
    local_ctx = LocalContextMiddleware(working_dir=str(tmp_path), enabled=True)
    agent = DeepAgent(
        config=cfg,
        agent=fake,  # type: ignore[arg-type]
        middlewares={"local_context": local_ctx},
        _skip_deprecation=True,
    )

    await agent.run("Implement feature", session_id="sess")
    await agent.run("Continue", session_id="sess")

    first = fake.calls[0]["payload"]["message"]
    second = fake.calls[1]["payload"]["message"]
    assert "<local-context>" in first
    assert "<local-context>" not in second


def test_tracing_event_order() -> None:
    tracing = TracingMiddleware(enabled=True, emit_langfuse=False)
    tracing.start_run("s-order")
    tracing.record("a", {"v": 1})
    tracing.record("b", {"v": 2})
    tracing.end_run(success=True)
    seqs = [e.seq for e in tracing.events]
    assert seqs == sorted(seqs)
    assert tracing.events[0].event_type == "run-start"
    assert tracing.events[-1].event_type == "run-end"


def test_tracing_end_run_flushes_langfuse_client() -> None:
    tracing = TracingMiddleware(enabled=True, emit_langfuse=False)

    class _FakeLangfuse:
        def __init__(self) -> None:
            self.flushed = False

        def event(self, **kwargs: Any) -> None:
            return None

        def flush(self) -> None:
            self.flushed = True

    fake = _FakeLangfuse()
    tracing._langfuse_client = fake  # type: ignore[attr-defined]
    tracing.start_run("s-flush")
    tracing.end_run(success=True)
    assert fake.flushed is True


def test_tracing_uses_langfuse_create_event_with_trace_context() -> None:
    tracing = TracingMiddleware(enabled=True, emit_langfuse=False)

    class _FakeLangfuse:
        def __init__(self) -> None:
            self.calls: List[Dict[str, Any]] = []

        def create_trace_id(self, seed: str) -> str:
            return f"lf-{seed}"

        def create_event(self, **kwargs: Any) -> None:
            self.calls.append(kwargs)

        def flush(self) -> None:
            return None

    fake = _FakeLangfuse()
    tracing._langfuse_client = fake  # type: ignore[attr-defined]
    tracing.start_run("s-lf")
    tracing.record("tool-start", {"tool_name": "read_file"})
    tracing.end_run(success=True)

    assert fake.calls
    first = fake.calls[0]
    assert first["name"].startswith("vel_harness.")
    assert first["trace_context"]["trace_id"].startswith("lf-run_")


def test_tracing_emits_outputs_for_run_end_and_tools() -> None:
    tracing = TracingMiddleware(enabled=True, emit_langfuse=False)

    class _FakeLangfuse:
        def __init__(self) -> None:
            self.calls: List[Dict[str, Any]] = []

        def create_trace_id(self, seed: str) -> str:
            return f"lf-{seed}"

        def create_event(self, **kwargs: Any) -> None:
            self.calls.append(kwargs)

        def flush(self) -> None:
            return None

    fake = _FakeLangfuse()
    tracing._langfuse_client = fake  # type: ignore[attr-defined]

    tracing.start_run("s-out")
    tracing.record_tool_success("read_file", {"path": "README.md"}, 1.0, {"content": "hello"})
    tracing.record_tool_failure("execute", {"command": "pytest"}, "boom", 2.0, error_type="RuntimeError")
    tracing.end_run(success=True, data={"final_output_preview": "final answer"})

    summaries = [c for c in fake.calls if c.get("name") == "vel_harness.tool_call_summary"]
    assert len(summaries) == 2
    statuses = {c["output"]["status"] for c in summaries}
    assert statuses == {"success", "failure"}
    run_end = [c for c in fake.calls if c.get("name") == "vel_harness.run-end"][-1]
    assert run_end["output"] == "final answer"


def test_debug_telemetry_preserves_verbose_tool_events() -> None:
    tracing = TracingMiddleware(
        enabled=True,
        emit_langfuse=False,
        telemetry_mode=TELEMETRY_MODE_DEBUG,
    )
    tracing.start_run("s-debug")
    tracing.record_tool_start("read_file", {"path": "README.md"})
    tracing.record_tool_success("read_file", {"path": "README.md"}, 1.0, {"content": "ok"})
    tracing.end_run(success=True)
    event_types = [e.event_type for e in tracing.events]
    assert "tool-start" in event_types
    assert "tool-success" in event_types
