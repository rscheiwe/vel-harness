"""
Runtime wiring tests for DeepAgent.

These tests focus on behavior in DeepAgent.run/run_stream:
- Context middleware preprocessing/postprocessing
- Prompted reasoning parsing in streaming and non-streaming paths
- Tool-output truncation hook
- finally semantics when underlying agent errors
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from vel_harness.config import DeepAgentConfig
from vel_harness.factory import DeepAgent


async def _agen(events):
    for event in events:
        yield event


def _make_deep_agent(
    *,
    reasoning: str | dict | None = None,
    stream_events=None,
    run_response: str = "ok",
):
    cfg_dict = {"name": "rt-test"}
    if reasoning is not None:
        cfg_dict["reasoning"] = reasoning
    config = DeepAgentConfig.from_dict(cfg_dict)

    agent = MagicMock()
    agent.ctxmgr = MagicMock()
    agent.ctxmgr.get_session_context.return_value = [{"role": "user", "content": "hello"}]
    agent.ctxmgr.set_session_context = MagicMock()

    response_obj = MagicMock()
    response_obj.content = run_response
    agent.run = AsyncMock(return_value=response_obj)
    agent.run_stream = MagicMock(return_value=_agen(stream_events or []))

    skills = MagicMock()
    skills.process_context = MagicMock()
    skills.get_system_prompt_segment.return_value = ""
    skills.get_state.return_value = {}
    skills.load_state.return_value = None

    context = MagicMock()
    context.process_messages = AsyncMock(return_value=[{"role": "user", "content": "preprocessed"}])
    context.after_assistant_response = AsyncMock(return_value=[{"role": "assistant", "content": "postprocessed"}])
    context.process_tool_result = MagicMock(side_effect=lambda content, tool_name, tool_call_id: content)
    context.get_system_prompt_segment.return_value = ""
    context.get_state.return_value = {}
    context.load_state.return_value = None

    deep = DeepAgent(
        config=config,
        agent=agent,
        middlewares={"skills": skills, "context": context},
        _skip_deprecation=True,
    )
    return deep, agent, skills, context


@pytest.mark.asyncio
async def test_run_applies_context_hooks_and_skill_processing():
    deep, agent, skills, context = _make_deep_agent()
    result = await deep.run("analyze this", session_id="s1")

    assert result.content == "ok"
    skills.process_context.assert_called_once_with("analyze this")
    context.process_messages.assert_awaited_once()
    context.after_assistant_response.assert_awaited_once()
    agent.ctxmgr.set_session_context.assert_called()
    agent.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_postprocess_runs_on_error():
    deep, agent, _, context = _make_deep_agent()
    agent.run = AsyncMock(side_effect=RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom"):
        await deep.run("fail please", session_id="s2")

    context.after_assistant_response.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_strips_prompted_reasoning_tags_non_streaming():
    deep, _, _, _ = _make_deep_agent(
        reasoning="prompted",
        run_response="<thinking>internal</thinking>final answer",
    )
    result = await deep.run("question", session_id="s3")
    assert result.content.strip() == "final answer"


@pytest.mark.asyncio
async def test_run_stream_parses_prompted_reasoning_events():
    deep, _, _, _ = _make_deep_agent(
        reasoning="prompted",
        stream_events=[
            {"type": "text-delta", "delta": "<thinking>step</thinking>answer"},
            {"type": "finish", "finishReason": "stop"},
        ],
    )

    events = []
    async for event in deep.run_stream("go", session_id="s4"):
        events.append(event)

    types = [e.get("type") for e in events if isinstance(e, dict)]
    assert "reasoning-start" in types
    assert "reasoning-delta" in types
    assert "reasoning-end" in types
    assert any(e.get("type") == "text-delta" and "answer" in e.get("delta", "") for e in events)


@pytest.mark.asyncio
async def test_run_stream_hides_reasoning_when_disabled():
    deep, _, _, _ = _make_deep_agent(
        reasoning={"mode": "prompted", "stream_reasoning": False},
        stream_events=[
            {"type": "text-delta", "delta": "<thinking>secret</thinking>visible"},
            {"type": "finish", "finishReason": "stop"},
        ],
    )

    events = []
    async for event in deep.run_stream("go", session_id="s5"):
        events.append(event)

    types = [e.get("type") for e in events if isinstance(e, dict)]
    assert "reasoning-start" not in types
    assert "reasoning-delta" not in types
    assert "reasoning-end" not in types
    assert any(e.get("type") == "text-delta" and "visible" in e.get("delta", "") for e in events)


@pytest.mark.asyncio
async def test_run_stream_applies_tool_output_truncation():
    deep, _, _, context = _make_deep_agent(
        stream_events=[
            {"type": "tool-output-available", "toolName": "grep", "toolCallId": "t1", "output": "very long"},
            {"type": "finish", "finishReason": "stop"},
        ],
    )
    context.process_tool_result = MagicMock(return_value="truncated")

    events = []
    async for event in deep.run_stream("go", session_id="s6"):
        events.append(event)

    tool_events = [e for e in events if isinstance(e, dict) and e.get("type") == "tool-output-available"]
    assert len(tool_events) == 1
    assert tool_events[0]["output"] == "truncated"
