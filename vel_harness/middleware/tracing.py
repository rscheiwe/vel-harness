"""
Tracing middleware for ordered harness events.

Provides lightweight, structured run tracing with optional Langfuse emission.
Events are always stored in-memory for local debugging and tests.
"""

from __future__ import annotations

import contextvars
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from vel_harness.middleware.base import BaseMiddleware


_current_trace_run: contextvars.ContextVar[Optional[Dict[str, str]]] = contextvars.ContextVar(
    "vel_harness_trace_run",
    default=None,
)


@dataclass
class TraceEvent:
    """A single ordered trace event."""

    seq: int
    event_type: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    run_id: str = ""
    session_id: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


class TracingMiddleware(BaseMiddleware):
    """Structured tracing with ordered event sequence numbers."""

    def __init__(
        self,
        enabled: bool = True,
        emit_langfuse: bool = False,
        stream_mode: str = "compact",
    ) -> None:
        self._enabled = enabled
        self._emit_langfuse = emit_langfuse
        self._stream_mode = stream_mode
        self._seq = 0
        self._events: List[TraceEvent] = []
        self._session_tool_calls: Dict[str, int] = {}
        self._stream_state: Dict[str, Dict[str, Any]] = {}
        self._langfuse_client = self._create_langfuse_client() if emit_langfuse else None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def events(self) -> List[TraceEvent]:
        return list(self._events)

    def start_run(self, session_id: str) -> Dict[str, str]:
        """Start a trace run and bind it to contextvars."""
        run_ctx = {"run_id": f"run_{uuid.uuid4().hex[:12]}", "session_id": session_id}
        lf_trace_id = self._create_langfuse_trace_id(run_ctx["run_id"])
        if lf_trace_id:
            run_ctx["langfuse_trace_id"] = lf_trace_id
        self._session_tool_calls[session_id] = 0
        self._stream_state[session_id] = {
            "step_index": 0,
            "segment_index": 0,
            "text_chunks": [],
            "reasoning_chunks": [],
            "tool_inputs": {},
        }
        _current_trace_run.set(run_ctx)
        self.record("run-start", data={})
        return run_ctx

    def end_run(self, success: bool, data: Optional[Dict[str, Any]] = None) -> None:
        """Close trace run."""
        ctx = _current_trace_run.get() or {}
        sid = str(ctx.get("session_id", "") or "")
        if sid:
            self._flush_generation_segment(sid, trigger="run-end")
        self.record("run-end", data={"success": success, **(data or {})})
        self._flush_langfuse()
        _current_trace_run.set(None)

    def record(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Record a structured event."""
        if not self._enabled:
            return
        self._seq += 1
        ctx = _current_trace_run.get() or {}
        event = TraceEvent(
            seq=self._seq,
            event_type=event_type,
            run_id=ctx.get("run_id", ""),
            session_id=ctx.get("session_id", ""),
            data=data or {},
        )
        self._events.append(event)
        self._emit_to_langfuse(event)

    def record_tool_start(self, tool_name: str, tool_input: Dict[str, Any]) -> None:
        ctx = _current_trace_run.get() or {}
        sid = str(ctx.get("session_id", "") or "")
        if sid:
            self._session_tool_calls[sid] = self._session_tool_calls.get(sid, 0) + 1
        self.record("tool-start", {"tool_name": tool_name, "tool_input": tool_input})

    def record_tool_success(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        duration_ms: float,
        tool_output: Any = None,
    ) -> None:
        self.record(
            "tool-success",
            {
                "tool_name": tool_name,
                "tool_input": tool_input,
                "duration_ms": duration_ms,
                "tool_output_preview": self._preview_payload(tool_output),
            },
        )

    def record_tool_failure(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        error: str,
        duration_ms: float,
        error_type: str = "",
    ) -> None:
        self.record(
            "tool-failure",
            {
                "tool_name": tool_name,
                "tool_input": tool_input,
                "error": error,
                "error_type": error_type,
                "duration_ms": duration_ms,
            },
        )

    def has_tool_calls(self, session_id: str) -> bool:
        return self._session_tool_calls.get(session_id, 0) > 0

    def record_stream_event(self, session_id: str, event: Dict[str, Any]) -> None:
        """Record normalized stream events in ordered timeline."""
        if not self._enabled or not isinstance(event, dict):
            return
        stream_type = str(event.get("type", "unknown"))
        if self._stream_mode == "compact":
            self._record_stream_compact(session_id, event)
            return
        stage = "post_tool" if self.has_tool_calls(session_id) else "pre_tool"
        event_type = self._map_stream_event_type(stream_type)
        data: Dict[str, Any] = {
            "stream_type": stream_type,
            "stage": stage,
        }
        if stream_type in {"text-delta", "reasoning-delta"}:
            data["delta"] = str(event.get("delta", ""))[:2000]
        elif stream_type in {"reasoning-start", "reasoning-end"}:
            data["reasoning_id"] = str(event.get("id", ""))
        elif stream_type == "status":
            data["status"] = str(event.get("status", ""))
            data["message"] = str(event.get("message", ""))[:2000]
        elif stream_type in {"tool-output-available", "tool-call", "tool-call-start"}:
            data["tool_name"] = str(event.get("toolName", event.get("tool_name", "")))
            data["tool_call_id"] = str(event.get("toolCallId", event.get("tool_call_id", "")))
            if "output" in event:
                data["output_preview"] = self._preview_payload(event.get("output"), max_chars=2000)
        else:
            data["payload_preview"] = self._preview_payload(event, max_chars=2000)
        self.record(event_type, data)

    def _record_stream_compact(self, session_id: str, event: Dict[str, Any]) -> None:
        stream_type = str(event.get("type", "unknown"))
        state = self._stream_state.setdefault(
            session_id,
            {
                "step_index": 0,
                "segment_index": 0,
                "text_chunks": [],
                "reasoning_chunks": [],
                "tool_inputs": {},
            },
        )

        if stream_type == "start-step":
            self._flush_generation_segment(session_id, trigger="start-step")
            state["step_index"] = int(state.get("step_index", 0)) + 1
            state["segment_index"] = 0
            state["tool_inputs"] = {}
            return

        if stream_type == "text-delta":
            state["text_chunks"].append(str(event.get("delta", "")))
            return

        if stream_type == "reasoning-delta":
            state["reasoning_chunks"].append(str(event.get("delta", "")))
            return

        if stream_type in {"tool-input-start", "tool-call", "tool-call-start"}:
            self._flush_generation_segment(session_id, trigger="tool-boundary")
            tool_call_id = str(event.get("toolCallId", event.get("tool_call_id", "")))
            if tool_call_id:
                tool_inputs = state.setdefault("tool_inputs", {})
                tool_inputs[tool_call_id] = {
                    "tool_name": str(event.get("toolName", event.get("tool_name", ""))),
                    "input_deltas": [],
                }
            return

        if stream_type == "tool-input-delta":
            tool_call_id = str(event.get("toolCallId", event.get("tool_call_id", "")))
            if tool_call_id:
                tool_inputs = state.setdefault("tool_inputs", {})
                ti = tool_inputs.setdefault(tool_call_id, {"tool_name": "", "input_deltas": []})
                ti.setdefault("input_deltas", []).append(str(event.get("inputTextDelta", "")))
            return

        if stream_type == "tool-input-available":
            self._flush_generation_segment(session_id, trigger="tool-boundary")
            tool_call_id = str(event.get("toolCallId", event.get("tool_call_id", "")))
            tool_name = str(event.get("toolName", event.get("tool_name", "")))
            payload_input = event.get("input")
            if not payload_input and tool_call_id:
                tool_inputs = state.setdefault("tool_inputs", {})
                ti = tool_inputs.get(tool_call_id, {})
                raw = "".join(ti.get("input_deltas", []))
                if raw:
                    try:
                        payload_input = json.loads(raw)
                    except Exception:
                        payload_input = {"raw_input": raw}
                if not tool_name:
                    tool_name = str(ti.get("tool_name", ""))
            self.record(
                "assistant-tool-call",
                {
                    "stream_type": stream_type,
                    "step_index": int(state.get("step_index", 0)),
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "tool_input": payload_input or {},
                },
            )
            return

        if stream_type == "tool-output-available":
            tool_call_id = str(event.get("toolCallId", event.get("tool_call_id", "")))
            tool_name = ""
            if tool_call_id:
                tool_name = str(
                    state.setdefault("tool_inputs", {}).get(tool_call_id, {}).get("tool_name", "")
                )
            self.record(
                "assistant-tool-result",
                {
                    "stream_type": stream_type,
                    "step_index": int(state.get("step_index", 0)),
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "tool_output_preview": self._preview_payload(event.get("output"), max_chars=2000),
                },
            )
            return

        if stream_type == "finish-step":
            self._flush_generation_segment(session_id, trigger="finish-step")
            return

        if stream_type == "finish":
            self._flush_generation_segment(session_id, trigger="finish")
            return

    def _flush_generation_segment(self, session_id: str, trigger: str) -> None:
        state = self._stream_state.get(session_id)
        if not state:
            return
        text = "".join(state.get("text_chunks", []))
        reasoning = "".join(state.get("reasoning_chunks", []))
        if not text and not reasoning:
            return
        self.record(
            "assistant-generation",
            {
                "step_index": int(state.get("step_index", 0)),
                "segment_index": int(state.get("segment_index", 0)),
                "trigger": trigger,
                "text_chars": len(text),
                "text_preview": text[:6000],
                "reasoning_chars": len(reasoning),
                "reasoning_preview": reasoning[:3000],
            },
        )
        state["segment_index"] = int(state.get("segment_index", 0)) + 1
        state["text_chunks"] = []
        state["reasoning_chunks"] = []

    def get_state(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "emit_langfuse": self._emit_langfuse,
            "seq": self._seq,
            "events": [asdict(e) for e in self._events[-1000:]],
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        self._enabled = bool(state.get("enabled", True))
        self._emit_langfuse = bool(state.get("emit_langfuse", False))
        self._seq = int(state.get("seq", 0))
        restored = state.get("events", [])
        self._events = [
            TraceEvent(
                seq=e.get("seq", 0),
                event_type=e.get("event_type", "unknown"),
                timestamp=e.get("timestamp", ""),
                run_id=e.get("run_id", ""),
                session_id=e.get("session_id", ""),
                data=e.get("data", {}),
            )
            for e in restored
            if isinstance(e, dict)
        ]
        self._session_tool_calls = {}

    def _create_langfuse_client(self) -> Any:
        try:
            from langfuse import Langfuse

            return Langfuse()
        except Exception:
            return None

    def _emit_to_langfuse(self, event: TraceEvent) -> None:
        if self._langfuse_client is None:
            return
        try:
            payload = {
                "name": f"vel_harness.{event.event_type}",
                "input": event.data,
                "metadata": {
                    "seq": event.seq,
                    "run_id": event.run_id,
                    "session_id": event.session_id,
                    "timestamp": event.timestamp,
                },
            }
            output_payload = self._event_output_payload(event)
            if output_payload is not None:
                payload["output"] = output_payload

            # SDK v3 API.
            create_event = getattr(self._langfuse_client, "create_event", None)
            if callable(create_event):
                trace_ctx = _current_trace_run.get() or {}
                lf_trace_id = trace_ctx.get("langfuse_trace_id")
                if lf_trace_id:
                    payload["trace_context"] = {"trace_id": lf_trace_id}
                create_event(**payload)
                return

            # Legacy API fallback.
            legacy_event = getattr(self._langfuse_client, "event", None)
            if callable(legacy_event):
                legacy_event(**payload)
        except Exception:
            return

    def _flush_langfuse(self) -> None:
        """Best-effort flush to avoid event loss in short-lived processes."""
        if self._langfuse_client is None:
            return
        flush = getattr(self._langfuse_client, "flush", None)
        if not callable(flush):
            return
        try:
            flush()
        except Exception:
            return

    def _create_langfuse_trace_id(self, seed: str) -> str:
        """Create a stable Langfuse trace id for this run when supported."""
        if self._langfuse_client is None:
            return ""
        create_trace_id = getattr(self._langfuse_client, "create_trace_id", None)
        if not callable(create_trace_id):
            return ""
        try:
            return str(create_trace_id(seed=seed))
        except Exception:
            return ""

    def _map_stream_event_type(self, stream_type: str) -> str:
        mapping = {
            "text-delta": "assistant-text-delta",
            "assistant-message": "assistant-message",
            "reasoning-start": "assistant-reasoning-start",
            "reasoning-delta": "assistant-reasoning-delta",
            "reasoning-end": "assistant-reasoning-end",
            "status": "assistant-status",
            "finish": "assistant-finish",
            "tool-output-available": "assistant-tool-output-stream",
            "tool-call": "assistant-tool-call-stream",
            "tool-call-start": "assistant-tool-call-start-stream",
        }
        return mapping.get(stream_type, f"assistant-stream-{stream_type}")

    def _event_output_payload(self, event: TraceEvent) -> Any:
        if event.event_type == "run-end":
            return event.data.get("final_output_preview")
        if event.event_type == "tool-success":
            return event.data.get("tool_output_preview")
        if event.event_type == "tool-failure":
            return {
                "error": event.data.get("error"),
                "error_type": event.data.get("error_type"),
            }
        return None

    def _preview_payload(self, payload: Any, max_chars: int = 6000) -> str:
        if payload is None:
            return ""
        try:
            if isinstance(payload, str):
                text = payload
            else:
                text = json.dumps(payload, default=str, ensure_ascii=False)
        except Exception:
            text = str(payload)
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars]}...<truncated>"
