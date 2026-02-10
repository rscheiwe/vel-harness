"""
Vel Harness Reasoning - Unified reasoning configuration.

Supports 4 modes:
- native: Anthropic extended thinking (thinking blocks via API)
- reflection: Multi-pass reasoning via vel's ReflectionController
- prompted: Provider-agnostic CoT via prompt injection + stream parsing
- none: Standard execution (default)

The prompted mode is the key addition — it bootstraps extended-thinking-like
behavior from scratch by injecting a CoT prompt and parsing the model's output
to separate reasoning from the final answer. Works with ANY model.

Usage:
    from vel_harness.reasoning import ReasoningConfig

    # Native (Anthropic only)
    config = ReasoningConfig(mode="native", budget_tokens=10000)

    # Reflection (any model, multi-pass)
    config = ReasoningConfig(mode="reflection", max_refinements=3)

    # Prompted (any model, single-pass CoT)
    config = ReasoningConfig(mode="prompted")

    # String shorthand
    config = ReasoningConfig.from_value("prompted")
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Union


# --- System prompt for prompted reasoning ---

PROMPTED_REASONING_PROMPT = """Before answering, think through your reasoning step by step.
Wrap your internal reasoning in <thinking></thinking> tags.
Your reasoning will not be shown to the user — only your final answer outside the tags will be visible.

Example format:
<thinking>
Let me analyze this step by step...
[your reasoning here]
</thinking>

[Your final answer here]"""


# --- Delimiters ---


@dataclass
class ReasoningDelimiters:
    """Configurable delimiters for parsing thinking vs answer.

    Supports XML tags (default) and JSON format.
    Auto mode tries XML first, falls back to JSON.
    """

    format: Literal["xml", "json", "auto"] = "auto"

    # XML mode
    xml_open: str = "<thinking>"
    xml_close: str = "</thinking>"

    # JSON mode — expects {"thinking": "...", "answer": "..."}
    thinking_key: str = "thinking"
    answer_key: str = "answer"


# --- Config ---


@dataclass
class ReasoningConfig:
    """Unified reasoning configuration.

    Args:
        mode: Reasoning mode
            - "native": Anthropic extended thinking (thinking blocks via API)
            - "reflection": Multi-pass via ReflectionController (any model)
            - "prompted": CoT via prompt injection + stream parsing (any model)
            - "none": Standard execution (default)
        budget_tokens: Max thinking tokens for native mode
        max_refinements: Max refine iterations for reflection mode (1-5)
        confidence_threshold: Early-stop threshold for reflection (0-1)
        thinking_model: Optional cheaper model for thinking phases
        thinking_tools: Allow tool calls during thinking (reflection mode)
        prompt_template: Custom prompt for prompted mode (overrides default)
        delimiters: Delimiter config for prompted mode parsing
        stream_reasoning: Emit reasoning-* events during prompted mode
        transient: Mark reasoning events as transient (not saved to history)
    """

    mode: Literal["native", "reflection", "prompted", "none"] = "none"

    # Native mode (Anthropic extended thinking)
    budget_tokens: Optional[int] = None

    # Reflection mode
    max_refinements: int = 3
    confidence_threshold: float = 0.85
    thinking_model: Optional[Dict[str, Any]] = None
    thinking_tools: bool = True

    # Prompted mode
    prompt_template: Optional[str] = None
    delimiters: ReasoningDelimiters = field(default_factory=ReasoningDelimiters)
    stream_reasoning: bool = True
    transient: bool = True

    @classmethod
    def from_value(
        cls, value: Union[str, Dict[str, Any], "ReasoningConfig", None]
    ) -> "ReasoningConfig":
        """Create ReasoningConfig from various input formats.

        Args:
            value: One of:
                - String shorthand: "native", "reflection", "prompted", "none"
                - Dict with config fields
                - ReasoningConfig instance (passthrough)
                - None (returns default/none)
        """
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(mode=value)  # type: ignore[arg-type]
        if isinstance(value, dict):
            delimiters_data = value.pop("delimiters", None)
            delimiters = ReasoningDelimiters()
            if isinstance(delimiters_data, dict):
                delimiters = ReasoningDelimiters(
                    format=delimiters_data.get("format", "auto"),
                    xml_open=delimiters_data.get("xml_open", "<thinking>"),
                    xml_close=delimiters_data.get("xml_close", "</thinking>"),
                    thinking_key=delimiters_data.get("thinking_key", "thinking"),
                    answer_key=delimiters_data.get("answer_key", "answer"),
                )
            return cls(delimiters=delimiters, **value)
        return cls()


# --- Prompted Reasoning Parser ---


class PromptedReasoningParser:
    """Streaming parser that separates thinking from answer in real-time.

    Processes text deltas from LLM output and emits stream events:
    - reasoning-start: When thinking section begins
    - reasoning-delta: Thinking content chunks
    - reasoning-end: When thinking section closes
    - text-delta: Answer content (outside thinking tags)

    Handles partial tags across chunk boundaries (e.g., '<think' then 'ing>').

    Usage:
        parser = PromptedReasoningParser(config)
        for delta in llm_stream:
            events = parser.feed(delta)
            for event in events:
                yield event
        # Flush remaining buffer
        events = parser.finish()
        for event in events:
            yield event
    """

    def __init__(self, config: ReasoningConfig):
        self._config = config
        self._delimiters = config.delimiters
        self._state: Literal["detecting", "reasoning", "answering"] = "detecting"
        self._buffer = ""
        self._reasoning_id = str(uuid.uuid4())
        self._transient = config.transient
        self._started = False

    def feed(self, delta: str) -> List[Dict[str, Any]]:
        """Feed a text delta, return stream events.

        Args:
            delta: Text chunk from LLM stream

        Returns:
            List of event dicts (reasoning-start, reasoning-delta,
            reasoning-end, text-delta)
        """
        self._buffer += delta
        events: List[Dict[str, Any]] = []

        if self._delimiters.format == "json":
            # JSON mode deferred to finish() — need complete output
            return events

        # XML mode (or auto mode trying XML)
        events.extend(self._parse_xml())
        return events

    def finish(self) -> List[Dict[str, Any]]:
        """Flush remaining buffer and finalize.

        Call this when the LLM stream ends to process any remaining content.
        """
        events: List[Dict[str, Any]] = []

        if self._delimiters.format == "json" or (
            self._delimiters.format == "auto" and self._state == "detecting"
        ):
            # Try JSON parsing on complete buffer
            events.extend(self._parse_json())
        else:
            # Flush remaining XML buffer
            events.extend(self._flush_xml())

        return events

    def _parse_xml(self) -> List[Dict[str, Any]]:
        """Parse XML-style thinking tags from buffer."""
        events: List[Dict[str, Any]] = []
        open_tag = self._delimiters.xml_open
        close_tag = self._delimiters.xml_close

        while True:
            if self._state == "detecting":
                # Look for opening tag
                idx = self._buffer.find(open_tag)
                if idx >= 0:
                    # Emit any text before the tag as answer
                    prefix = self._buffer[:idx].strip()
                    if prefix:
                        events.append(self._text_event(prefix))
                    self._buffer = self._buffer[idx + len(open_tag):]
                    self._state = "reasoning"
                    events.append(self._reasoning_start_event())
                elif self._could_be_partial_tag(self._buffer, open_tag):
                    # Buffer might contain partial opening tag — wait for more data
                    break
                else:
                    # No tag found and no partial
                    if self._delimiters.format == "auto":
                        # In auto mode, hold buffer — might be JSON parsed in finish()
                        break
                    # In explicit XML mode, emit as answer text
                    if self._buffer:
                        events.append(self._text_event(self._buffer))
                        self._buffer = ""
                    break

            elif self._state == "reasoning":
                # Look for closing tag
                idx = self._buffer.find(close_tag)
                if idx >= 0:
                    # Emit reasoning content
                    reasoning = self._buffer[:idx]
                    if reasoning:
                        events.append(self._reasoning_delta_event(reasoning))
                    self._buffer = self._buffer[idx + len(close_tag):]
                    events.append(self._reasoning_end_event())
                    self._state = "answering"
                elif self._could_be_partial_tag(self._buffer, close_tag):
                    # Might be partial closing tag — flush safe prefix
                    safe_len = len(self._buffer) - len(close_tag) + 1
                    if safe_len > 0:
                        events.append(
                            self._reasoning_delta_event(self._buffer[:safe_len])
                        )
                        self._buffer = self._buffer[safe_len:]
                    break
                else:
                    # No closing tag yet — emit buffer as reasoning delta
                    if self._buffer:
                        events.append(self._reasoning_delta_event(self._buffer))
                        self._buffer = ""
                    break

            elif self._state == "answering":
                # Everything after closing tag is answer
                if self._buffer:
                    text = self._buffer.lstrip()
                    if text:
                        events.append(self._text_event(text))
                    self._buffer = ""
                break

        return events

    def _flush_xml(self) -> List[Dict[str, Any]]:
        """Flush remaining XML buffer at end of stream."""
        events: List[Dict[str, Any]] = []

        if self._state == "reasoning":
            # Unclosed thinking tag — emit remaining as reasoning and close
            if self._buffer:
                events.append(self._reasoning_delta_event(self._buffer))
                self._buffer = ""
            events.append(self._reasoning_end_event())
        elif self._state == "detecting" and self._buffer:
            # Never found tags — emit as plain text
            events.append(self._text_event(self._buffer))
            self._buffer = ""
        elif self._state == "answering" and self._buffer:
            events.append(self._text_event(self._buffer))
            self._buffer = ""

        return events

    def _parse_json(self) -> List[Dict[str, Any]]:
        """Parse JSON-style thinking/answer from complete buffer."""
        import json

        events: List[Dict[str, Any]] = []
        text = self._buffer.strip()

        try:
            data = json.loads(text)
            thinking = data.get(self._delimiters.thinking_key, "")
            answer = data.get(self._delimiters.answer_key, "")

            if thinking:
                events.append(self._reasoning_start_event())
                events.append(self._reasoning_delta_event(thinking))
                events.append(self._reasoning_end_event())

            if answer:
                events.append(self._text_event(answer))

            self._buffer = ""
        except (json.JSONDecodeError, AttributeError):
            # Not valid JSON — in auto mode, treat as plain text
            if self._buffer:
                events.append(self._text_event(self._buffer))
                self._buffer = ""

        return events

    @staticmethod
    def _could_be_partial_tag(buffer: str, tag: str) -> bool:
        """Check if the end of the buffer could be the start of a tag."""
        for i in range(1, len(tag)):
            if buffer.endswith(tag[:i]):
                return True
        return False

    def _reasoning_start_event(self) -> Dict[str, Any]:
        """Create a reasoning-start event."""
        self._started = True
        event: Dict[str, Any] = {
            "type": "reasoning-start",
            "id": self._reasoning_id,
        }
        if self._transient:
            event["transient"] = True
        return event

    def _reasoning_delta_event(self, delta: str) -> Dict[str, Any]:
        """Create a reasoning-delta event."""
        event: Dict[str, Any] = {
            "type": "reasoning-delta",
            "id": self._reasoning_id,
            "delta": delta,
        }
        if self._transient:
            event["transient"] = True
        return event

    def _reasoning_end_event(self) -> Dict[str, Any]:
        """Create a reasoning-end event."""
        event: Dict[str, Any] = {
            "type": "reasoning-end",
            "id": self._reasoning_id,
        }
        if self._transient:
            event["transient"] = True
        return event

    def _text_event(self, text: str) -> Dict[str, Any]:
        """Create a text-delta event."""
        return {
            "type": "text-delta",
            "delta": text,
        }
