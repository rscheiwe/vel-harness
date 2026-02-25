"""Tests for harness-strengthening configuration blocks."""

from vel_harness.config import DeepAgentConfig


def test_strengthening_config_defaults_present() -> None:
    cfg = DeepAgentConfig()
    assert cfg.local_context.enabled is True
    assert cfg.loop_detection.enabled is True
    assert cfg.verification.enabled is True
    assert cfg.tracing.enabled is True
    assert cfg.reasoning_scheduler.enabled is True
    assert cfg.run_guard.enabled is True


def test_strengthening_config_roundtrip() -> None:
    cfg = DeepAgentConfig.from_dict(
        {
            "local_context": {"enabled": True, "max_entries": 12},
            "loop_detection": {"enabled": True, "file_edit_threshold": 7},
            "verification": {"enabled": True, "max_followups": 2},
            "tracing": {"enabled": True, "emit_langfuse": False},
            "reasoning_scheduler": {
                "enabled": True,
                "planning_budget_tokens": 111,
                "build_budget_tokens": 222,
                "verify_budget_tokens": 333,
            },
            "run_guard": {
                "enabled": True,
                "max_tool_calls_total": 9,
                "max_same_tool_input_repeats": 2,
                "max_failure_streak": 4,
                "max_discovery_rounds_by_class": {"data_retrieval": 1, "general": 2},
                "max_repeated_identical_execute": 2,
                "enforce_query_evidence_for_numeric_claims": True,
            },
        }
    )
    d = cfg.to_dict()
    assert d["local_context"]["max_entries"] == 12
    assert d["loop_detection"]["file_edit_threshold"] == 7
    assert d["verification"]["max_followups"] == 2
    assert d["tracing"]["enabled"] is True
    assert d["tracing"]["telemetry_mode"] == "standard"
    assert d["reasoning_scheduler"]["verify_budget_tokens"] == 333
    assert d["run_guard"]["max_tool_calls_total"] == 9
    assert d["run_guard"]["max_same_tool_input_repeats"] == 2
    assert d["run_guard"]["max_discovery_rounds_by_class"]["data_retrieval"] == 1
    assert d["run_guard"]["max_repeated_identical_execute"] == 2
    assert d["run_guard"]["enforce_query_evidence_for_numeric_claims"] is True
