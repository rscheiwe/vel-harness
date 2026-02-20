"""
Tests for Reasoning System (WS3)

Tests the unified reasoning configuration including:
- ReasoningConfig creation with all modes
- ReasoningDelimiters configuration
- PromptedReasoningParser XML streaming
- PromptedReasoningParser JSON parsing
- PromptedReasoningParser auto-detection
- Partial tag handling across chunk boundaries
- Transient flag on reasoning events
- DeepAgentConfig from_dict/to_dict for reasoning
- Factory wiring for native/reflection/prompted modes
- VelHarness integration with reasoning parameter
"""

import pytest
from unittest.mock import MagicMock, patch

from vel_harness.reasoning import (
    ReasoningConfig,
    ReasoningDelimiters,
    PromptedReasoningParser,
    PROMPTED_REASONING_PROMPT,
)
from vel_harness.config import DeepAgentConfig
from vel_harness.factory import create_deep_agent
from vel_harness import VelHarness


# --- ReasoningConfig Tests ---


class TestReasoningConfig:
    """Tests for ReasoningConfig dataclass."""

    def test_default_mode_is_none(self):
        """Test default reasoning mode is 'none'."""
        config = ReasoningConfig()
        assert config.mode == "none"
        assert config.budget_tokens is None
        assert config.max_refinements == 3
        assert config.confidence_threshold == 0.85
        assert config.thinking_model is None
        assert config.thinking_tools is True

    def test_native_mode(self):
        """Test native mode configuration."""
        config = ReasoningConfig(mode="native", budget_tokens=10000)
        assert config.mode == "native"
        assert config.budget_tokens == 10000

    def test_reflection_mode(self):
        """Test reflection mode configuration."""
        config = ReasoningConfig(
            mode="reflection",
            max_refinements=5,
            confidence_threshold=0.9,
            thinking_model={"provider": "openai", "model": "gpt-4o-mini"},
            thinking_tools=False,
        )
        assert config.mode == "reflection"
        assert config.max_refinements == 5
        assert config.confidence_threshold == 0.9
        assert config.thinking_model == {"provider": "openai", "model": "gpt-4o-mini"}
        assert config.thinking_tools is False

    def test_prompted_mode(self):
        """Test prompted mode configuration."""
        config = ReasoningConfig(mode="prompted")
        assert config.mode == "prompted"
        assert config.prompt_template is None
        assert config.stream_reasoning is True
        assert config.transient is True

    def test_prompted_mode_custom_template(self):
        """Test prompted mode with custom template."""
        custom = "Think carefully before answering."
        config = ReasoningConfig(mode="prompted", prompt_template=custom)
        assert config.prompt_template == custom

    def test_prompted_mode_custom_delimiters(self):
        """Test prompted mode with custom delimiters."""
        delims = ReasoningDelimiters(
            format="xml",
            xml_open="<reason>",
            xml_close="</reason>",
        )
        config = ReasoningConfig(mode="prompted", delimiters=delims)
        assert config.delimiters.xml_open == "<reason>"
        assert config.delimiters.xml_close == "</reason>"


# --- ReasoningConfig.from_value Tests ---


class TestReasoningConfigFromValue:
    """Tests for ReasoningConfig.from_value() factory method."""

    def test_from_none(self):
        """Test from_value(None) returns default config."""
        config = ReasoningConfig.from_value(None)
        assert config.mode == "none"

    def test_from_string_shorthand(self):
        """Test from_value with string shorthand."""
        assert ReasoningConfig.from_value("native").mode == "native"
        assert ReasoningConfig.from_value("reflection").mode == "reflection"
        assert ReasoningConfig.from_value("prompted").mode == "prompted"
        assert ReasoningConfig.from_value("none").mode == "none"

    def test_from_dict(self):
        """Test from_value with dictionary."""
        config = ReasoningConfig.from_value({
            "mode": "native",
            "budget_tokens": 5000,
        })
        assert config.mode == "native"
        assert config.budget_tokens == 5000

    def test_from_dict_with_delimiters(self):
        """Test from_value with dict including delimiters."""
        payload = {
            "mode": "prompted",
            "delimiters": {
                "format": "json",
                "thinking_key": "reason",
                "answer_key": "response",
            },
        }
        config = ReasoningConfig.from_value(payload)
        assert config.mode == "prompted"
        assert config.delimiters.format == "json"
        assert config.delimiters.thinking_key == "reason"
        assert config.delimiters.answer_key == "response"
        # Ensure input dict is not mutated.
        assert "delimiters" in payload

    def test_from_reasoning_config_passthrough(self):
        """Test from_value passes through ReasoningConfig instance."""
        original = ReasoningConfig(mode="prompted")
        result = ReasoningConfig.from_value(original)
        assert result is original

    def test_from_unknown_type_returns_default(self):
        """Test from_value with unknown type returns default."""
        config = ReasoningConfig.from_value(42)
        assert config.mode == "none"


# --- ReasoningDelimiters Tests ---


class TestReasoningDelimiters:
    """Tests for ReasoningDelimiters dataclass."""

    def test_defaults(self):
        """Test default delimiters."""
        delims = ReasoningDelimiters()
        assert delims.format == "auto"
        assert delims.xml_open == "<thinking>"
        assert delims.xml_close == "</thinking>"
        assert delims.thinking_key == "thinking"
        assert delims.answer_key == "answer"

    def test_xml_format(self):
        """Test XML format delimiters."""
        delims = ReasoningDelimiters(format="xml")
        assert delims.format == "xml"

    def test_json_format(self):
        """Test JSON format delimiters."""
        delims = ReasoningDelimiters(
            format="json",
            thinking_key="reasoning",
            answer_key="result",
        )
        assert delims.format == "json"
        assert delims.thinking_key == "reasoning"
        assert delims.answer_key == "result"

    def test_custom_xml_tags(self):
        """Test custom XML tag delimiters."""
        delims = ReasoningDelimiters(
            format="xml",
            xml_open="<reason>",
            xml_close="</reason>",
        )
        assert delims.xml_open == "<reason>"
        assert delims.xml_close == "</reason>"


# --- PromptedReasoningParser XML Tests ---


class TestPromptedReasoningParserXML:
    """Tests for PromptedReasoningParser with XML delimiters."""

    def _make_parser(self, **kwargs):
        """Create parser with XML config."""
        config = ReasoningConfig(mode="prompted", **kwargs)
        return PromptedReasoningParser(config)

    def test_simple_thinking_and_answer(self):
        """Test parsing complete thinking + answer."""
        parser = self._make_parser()
        events = parser.feed("<thinking>Step 1. Step 2.</thinking>The answer.")
        events += parser.finish()

        types = [e["type"] for e in events]
        assert "reasoning-start" in types
        assert "reasoning-delta" in types
        assert "reasoning-end" in types
        assert "text-delta" in types

        # Check reasoning content
        reasoning_deltas = [e["delta"] for e in events if e["type"] == "reasoning-delta"]
        assert "Step 1. Step 2." in "".join(reasoning_deltas)

        # Check answer content
        text_deltas = [e["delta"] for e in events if e["type"] == "text-delta"]
        assert "The answer." in "".join(text_deltas)

    def test_streaming_chunks(self):
        """Test streaming with multiple small chunks."""
        parser = self._make_parser()

        all_events = []
        all_events += parser.feed("<think")
        all_events += parser.feed("ing>")
        all_events += parser.feed("Let me think...")
        all_events += parser.feed("</think")
        all_events += parser.feed("ing>")
        all_events += parser.feed("Final answer.")
        all_events += parser.finish()

        types = [e["type"] for e in all_events]
        assert "reasoning-start" in types
        assert "reasoning-end" in types
        assert "text-delta" in types

    def test_no_thinking_tags(self):
        """Test output without thinking tags treated as plain text."""
        parser = self._make_parser()
        events = parser.feed("Just a regular answer.")
        events += parser.finish()

        types = [e["type"] for e in events]
        assert "reasoning-start" not in types
        assert "text-delta" in types

        text_deltas = [e["delta"] for e in events if e["type"] == "text-delta"]
        assert "Just a regular answer." in "".join(text_deltas)

    def test_text_before_thinking(self):
        """Test text appearing before thinking tags."""
        parser = self._make_parser()
        events = parser.feed("Prefix <thinking>reasoning</thinking>Answer")
        events += parser.finish()

        types = [e["type"] for e in events]
        # Prefix should be text-delta
        text_deltas = [e["delta"] for e in events if e["type"] == "text-delta"]
        combined = "".join(text_deltas)
        assert "Prefix" in combined
        assert "Answer" in combined

    def test_transient_flag(self):
        """Test transient flag on reasoning events."""
        parser = self._make_parser(transient=True)
        events = parser.feed("<thinking>think</thinking>answer")
        events += parser.finish()

        for event in events:
            if event["type"].startswith("reasoning-"):
                assert event.get("transient") is True
            elif event["type"] == "text-delta":
                assert "transient" not in event

    def test_non_transient(self):
        """Test reasoning events without transient flag."""
        parser = self._make_parser(transient=False)
        events = parser.feed("<thinking>think</thinking>answer")
        events += parser.finish()

        for event in events:
            assert event.get("transient") is not True

    def test_reasoning_id_consistent(self):
        """Test that all reasoning events share the same ID."""
        parser = self._make_parser()
        events = parser.feed("<thinking>step 1</thinking>done")
        events += parser.finish()

        reasoning_events = [e for e in events if e["type"].startswith("reasoning-")]
        ids = {e["id"] for e in reasoning_events}
        assert len(ids) == 1  # All share same ID

    def test_empty_thinking(self):
        """Test empty thinking tags."""
        parser = self._make_parser()
        events = parser.feed("<thinking></thinking>Just the answer.")
        events += parser.finish()

        types = [e["type"] for e in events]
        assert "reasoning-start" in types
        assert "reasoning-end" in types
        text_deltas = [e["delta"] for e in events if e["type"] == "text-delta"]
        assert "Just the answer." in "".join(text_deltas)

    def test_partial_open_tag_at_boundary(self):
        """Test partial opening tag that spans chunk boundaries."""
        parser = self._make_parser()

        # Feed '<' at the end — should buffer (could be partial <thinking>)
        events1 = parser.feed("Hello <")
        # Complete the tag
        events2 = parser.feed("thinking>reasoning</thinking>answer")
        events3 = parser.finish()

        all_events = events1 + events2 + events3
        types = [e["type"] for e in all_events]
        assert "reasoning-start" in types

    def test_partial_close_tag_at_boundary(self):
        """Test partial closing tag that spans chunk boundaries."""
        parser = self._make_parser()

        events = []
        events += parser.feed("<thinking>think about it</")
        events += parser.feed("thinking>the answer")
        events += parser.finish()

        types = [e["type"] for e in events]
        assert "reasoning-start" in types
        assert "reasoning-end" in types
        assert "text-delta" in types

    def test_unclosed_thinking_tag(self):
        """Test unclosed thinking tag at end of stream."""
        parser = self._make_parser()
        events = parser.feed("<thinking>started thinking but never closed")
        events += parser.finish()

        types = [e["type"] for e in events]
        assert "reasoning-start" in types
        assert "reasoning-end" in types  # finish() closes it

    def test_custom_xml_tags(self):
        """Test custom XML tag delimiters."""
        delims = ReasoningDelimiters(format="xml", xml_open="<reason>", xml_close="</reason>")
        parser = PromptedReasoningParser(
            ReasoningConfig(mode="prompted", delimiters=delims)
        )
        events = parser.feed("<reason>thinking here</reason>answer here")
        events += parser.finish()

        reasoning_deltas = [e["delta"] for e in events if e["type"] == "reasoning-delta"]
        text_deltas = [e["delta"] for e in events if e["type"] == "text-delta"]
        assert "thinking here" in "".join(reasoning_deltas)
        assert "answer here" in "".join(text_deltas)


# --- PromptedReasoningParser JSON Tests ---


class TestPromptedReasoningParserJSON:
    """Tests for PromptedReasoningParser with JSON mode."""

    def _make_parser(self, **kwargs):
        """Create parser with JSON config."""
        delims = ReasoningDelimiters(format="json")
        config = ReasoningConfig(mode="prompted", delimiters=delims, **kwargs)
        return PromptedReasoningParser(config)

    def test_json_thinking_and_answer(self):
        """Test JSON format parsing."""
        parser = self._make_parser()
        # JSON mode defers to finish()
        events = parser.feed('{"thinking": "Let me reason", "answer": "The result"}')
        assert events == []  # JSON defers to finish

        events = parser.finish()
        types = [e["type"] for e in events]
        assert "reasoning-start" in types
        assert "reasoning-delta" in types
        assert "reasoning-end" in types
        assert "text-delta" in types

        reasoning_deltas = [e["delta"] for e in events if e["type"] == "reasoning-delta"]
        assert "Let me reason" in "".join(reasoning_deltas)

        text_deltas = [e["delta"] for e in events if e["type"] == "text-delta"]
        assert "The result" in "".join(text_deltas)

    def test_json_only_answer(self):
        """Test JSON with only answer (no thinking)."""
        parser = self._make_parser()
        parser.feed('{"answer": "Direct answer"}')
        events = parser.finish()

        types = [e["type"] for e in events]
        assert "reasoning-start" not in types
        assert "text-delta" in types

    def test_json_only_thinking(self):
        """Test JSON with only thinking (no answer)."""
        parser = self._make_parser()
        parser.feed('{"thinking": "Just thinking"}')
        events = parser.finish()

        types = [e["type"] for e in events]
        assert "reasoning-start" in types
        assert "reasoning-end" in types
        assert "text-delta" not in types

    def test_invalid_json_treated_as_text(self):
        """Test invalid JSON treated as plain text."""
        parser = self._make_parser()
        parser.feed("Not JSON at all")
        events = parser.finish()

        types = [e["type"] for e in events]
        assert "reasoning-start" not in types
        assert "text-delta" in types

    def test_custom_json_keys(self):
        """Test custom JSON keys."""
        delims = ReasoningDelimiters(
            format="json",
            thinking_key="reasoning",
            answer_key="response",
        )
        config = ReasoningConfig(mode="prompted", delimiters=delims)
        parser = PromptedReasoningParser(config)

        parser.feed('{"reasoning": "My thoughts", "response": "My answer"}')
        events = parser.finish()

        reasoning_deltas = [e["delta"] for e in events if e["type"] == "reasoning-delta"]
        text_deltas = [e["delta"] for e in events if e["type"] == "text-delta"]
        assert "My thoughts" in "".join(reasoning_deltas)
        assert "My answer" in "".join(text_deltas)


# --- PromptedReasoningParser Auto Mode Tests ---


class TestPromptedReasoningParserAuto:
    """Tests for PromptedReasoningParser with auto-detection."""

    def _make_parser(self, **kwargs):
        """Create parser with auto config (default)."""
        config = ReasoningConfig(mode="prompted", **kwargs)
        return PromptedReasoningParser(config)

    def test_auto_detects_xml(self):
        """Test auto mode detects XML tags."""
        parser = self._make_parser()
        events = parser.feed("<thinking>reasoning</thinking>answer")
        events += parser.finish()

        types = [e["type"] for e in events]
        assert "reasoning-start" in types
        assert "reasoning-end" in types

    def test_auto_falls_back_to_json(self):
        """Test auto mode falls back to JSON when no XML tags found."""
        parser = self._make_parser()
        parser.feed('{"thinking": "thought", "answer": "result"}')
        events = parser.finish()

        types = [e["type"] for e in events]
        assert "reasoning-start" in types
        assert "text-delta" in types

    def test_auto_plain_text(self):
        """Test auto mode with plain text (no XML, not JSON)."""
        parser = self._make_parser()
        events = parser.feed("Just a plain answer without reasoning")
        events += parser.finish()

        types = [e["type"] for e in events]
        assert "reasoning-start" not in types
        assert "text-delta" in types


# --- PROMPTED_REASONING_PROMPT Tests ---


class TestPromptedReasoningPrompt:
    """Test the default prompted reasoning prompt."""

    def test_prompt_includes_thinking_tags(self):
        """Test prompt instructs model to use thinking tags."""
        assert "<thinking>" in PROMPTED_REASONING_PROMPT
        assert "</thinking>" in PROMPTED_REASONING_PROMPT

    def test_prompt_is_nonempty(self):
        """Test prompt is not empty."""
        assert len(PROMPTED_REASONING_PROMPT) > 50


# --- DeepAgentConfig Integration Tests ---


class TestDeepAgentConfigReasoning:
    """Tests for ReasoningConfig in DeepAgentConfig."""

    def test_default_no_reasoning(self):
        """Test default DeepAgentConfig has no reasoning."""
        config = DeepAgentConfig()
        assert config.reasoning is None

    def test_from_dict_string_shorthand(self):
        """Test from_dict with string reasoning shorthand."""
        config = DeepAgentConfig.from_dict({"reasoning": "prompted"})
        assert config.reasoning is not None
        assert config.reasoning.mode == "prompted"

    def test_from_dict_native(self):
        """Test from_dict with native reasoning config."""
        config = DeepAgentConfig.from_dict({
            "reasoning": {
                "mode": "native",
                "budget_tokens": 20000,
            },
        })
        assert config.reasoning.mode == "native"
        assert config.reasoning.budget_tokens == 20000

    def test_from_dict_reflection(self):
        """Test from_dict with reflection reasoning config."""
        config = DeepAgentConfig.from_dict({
            "reasoning": {
                "mode": "reflection",
                "max_refinements": 4,
                "confidence_threshold": 0.9,
            },
        })
        assert config.reasoning.mode == "reflection"
        assert config.reasoning.max_refinements == 4
        assert config.reasoning.confidence_threshold == 0.9

    def test_from_dict_reasoning_config_passthrough(self):
        """Test from_dict with ReasoningConfig instance."""
        rc = ReasoningConfig(mode="prompted")
        config = DeepAgentConfig.from_dict({"reasoning": rc})
        assert config.reasoning is rc

    def test_to_dict_with_reasoning(self):
        """Test to_dict includes reasoning."""
        config = DeepAgentConfig()
        config.reasoning = ReasoningConfig(mode="prompted")
        d = config.to_dict()
        assert d["reasoning"] is not None
        assert d["reasoning"]["mode"] == "prompted"

    def test_to_dict_without_reasoning(self):
        """Test to_dict without reasoning."""
        config = DeepAgentConfig()
        d = config.to_dict()
        assert d["reasoning"] is None

    def test_round_trip_native(self):
        """Test from_dict -> to_dict round trip for native mode."""
        original = {
            "reasoning": {
                "mode": "native",
                "budget_tokens": 15000,
            },
        }
        config = DeepAgentConfig.from_dict(original)
        d = config.to_dict()
        assert d["reasoning"]["mode"] == "native"


# --- Factory Integration Tests ---


class TestFactoryReasoningWiring:
    """Tests that reasoning is wired into the factory."""

    def test_no_reasoning_by_default(self):
        """Test factory works without reasoning config."""
        agent = create_deep_agent()
        assert agent is not None

    def test_prompted_mode_injects_prompt(self):
        """Test prompted mode injects reasoning prompt into system prompt."""
        config = DeepAgentConfig.from_dict({
            "reasoning": "prompted",
        })
        agent = create_deep_agent(config=config)
        assert agent is not None
        # The system prompt should contain the prompted reasoning prompt
        system_prompt = agent.agent._system_prompt
        if system_prompt:
            assert "<thinking>" in system_prompt

    def test_prompted_mode_custom_template(self):
        """Test prompted mode with custom prompt template."""
        custom_prompt = "Think step by step using <thought></thought> tags."
        config = DeepAgentConfig.from_dict({
            "reasoning": {
                "mode": "prompted",
                "prompt_template": custom_prompt,
            },
        })
        agent = create_deep_agent(config=config)
        assert agent is not None
        system_prompt = agent.agent._system_prompt
        if system_prompt:
            assert custom_prompt in system_prompt

    def test_native_mode_sets_generation_config(self):
        """Test native mode passes generation_config to Agent."""
        config = DeepAgentConfig.from_dict({
            "reasoning": {
                "mode": "native",
                "budget_tokens": 8000,
            },
        })
        agent = create_deep_agent(config=config)
        assert agent is not None
        # Agent should have generation_config with thinking
        gen_config = agent.agent.generation_config
        assert gen_config is not None
        assert "thinking" in gen_config
        assert gen_config["thinking"]["type"] == "enabled"
        assert gen_config["thinking"]["budget_tokens"] == 8000

    def test_native_mode_default_budget(self):
        """Test native mode uses default budget when none specified."""
        config = DeepAgentConfig.from_dict({
            "reasoning": "native",
        })
        agent = create_deep_agent(config=config)
        gen_config = agent.agent.generation_config
        assert gen_config["thinking"]["budget_tokens"] == 10000

    def test_reflection_mode_sets_thinking_config(self):
        """Test reflection mode passes ThinkingConfig to Agent."""
        config = DeepAgentConfig.from_dict({
            "reasoning": {
                "mode": "reflection",
                "max_refinements": 4,
                "confidence_threshold": 0.9,
            },
        })
        agent = create_deep_agent(config=config)
        assert agent is not None
        # Agent should have thinking config
        thinking = agent.agent.thinking_config
        assert thinking is not None
        assert thinking.mode == "reflection"
        assert thinking.max_refinements == 4
        assert thinking.confidence_threshold == 0.9

    def test_reflection_mode_with_thinking_model(self):
        """Test reflection mode with separate thinking model."""
        config = DeepAgentConfig.from_dict({
            "reasoning": {
                "mode": "reflection",
                "thinking_model": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
            },
        })
        agent = create_deep_agent(config=config)
        thinking = agent.agent.thinking_config
        assert thinking.thinking_model == {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"}

    def test_none_mode_no_extras(self):
        """Test none mode doesn't add generation_config or thinking."""
        config = DeepAgentConfig.from_dict({
            "reasoning": "none",
        })
        agent = create_deep_agent(config=config)
        # Should not have thinking-specific config
        gen_config = agent.agent.generation_config
        assert not gen_config or "thinking" not in gen_config


# --- VelHarness Integration Tests ---


class TestVelHarnessReasoning:
    """Tests for reasoning through VelHarness constructor."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock Vel Agent."""
        with patch("vel_harness.factory.Agent") as MockAgent:
            mock_instance = MagicMock()
            MockAgent.return_value = mock_instance
            yield MockAgent

    def test_no_reasoning_by_default(self, mock_agent):
        """Test VelHarness defaults to no reasoning."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
        )
        assert harness.reasoning_config is None

    def test_with_string_shorthand(self, mock_agent):
        """Test VelHarness with string reasoning shorthand."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            reasoning="prompted",
        )
        assert harness.reasoning_config is not None
        assert harness.reasoning_config.mode == "prompted"

    def test_with_dict_config(self, mock_agent):
        """Test VelHarness with dict reasoning config."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            reasoning={"mode": "native", "budget_tokens": 5000},
        )
        assert harness.reasoning_config is not None
        assert harness.reasoning_config.mode == "native"
        assert harness.reasoning_config.budget_tokens == 5000

    def test_with_reasoning_config_instance(self, mock_agent):
        """Test VelHarness with ReasoningConfig instance."""
        rc = ReasoningConfig(mode="reflection", max_refinements=2)
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            reasoning=rc,
        )
        assert harness.reasoning_config is rc
        assert harness.reasoning_config.max_refinements == 2

    def test_reasoning_with_hooks_and_caching(self, mock_agent):
        """Test reasoning coexists with hooks and caching."""
        from vel_harness.hooks import HookMatcher, HookResult
        from unittest.mock import AsyncMock

        handler = AsyncMock(return_value=HookResult(decision="allow"))
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            caching=True,
            retry=True,
            hooks={"pre_tool_use": [HookMatcher(handler=handler)]},
            reasoning="prompted",
        )
        assert harness.reasoning_config is not None
        assert harness.reasoning_config.mode == "prompted"
        assert harness.hook_engine is not None
        assert harness.config.caching.enabled is True
        assert harness.config.retry.enabled is True

    def test_reasoning_in_config(self, mock_agent):
        """Test reasoning config flows through to DeepAgentConfig."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
            reasoning="reflection",
        )
        assert harness.config.reasoning is not None
        assert harness.config.reasoning.mode == "reflection"
