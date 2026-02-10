"""
Subagents Tests

Tests for subagent spawner and middleware.
Note: These tests use mocks since actual subagent execution requires a full agent setup.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vel_harness.subagents.spawner import (
    SubagentConfig,
    SubagentResult,
    SubagentSpawner,
    SubagentStatus,
)
from vel_harness.middleware.subagents import SubagentsMiddleware


# SubagentResult Tests


class TestSubagentResult:
    """Tests for SubagentResult dataclass."""

    def test_successful_result(self) -> None:
        """Test creating a successful result."""
        result = SubagentResult(
            id="test_123",
            task="Research topic",
            status=SubagentStatus.COMPLETED,
            result="Found relevant information.",
            started_at=datetime(2024, 1, 1, 12, 0, 0),
            completed_at=datetime(2024, 1, 1, 12, 0, 30),
        )

        assert result.status == SubagentStatus.COMPLETED
        assert result.duration_seconds == 30.0

    def test_failed_result(self) -> None:
        """Test creating a failed result."""
        result = SubagentResult(
            id="test_456",
            task="Failed task",
            status=SubagentStatus.FAILED,
            error="Connection timeout",
        )

        assert result.status == SubagentStatus.FAILED
        assert result.error == "Connection timeout"
        assert result.duration_seconds is None

    def test_to_dict(self) -> None:
        """Test converting result to dictionary."""
        result = SubagentResult(
            id="test_789",
            task="Test task",
            status=SubagentStatus.COMPLETED,
            result="Done",
        )

        d = result.to_dict()

        assert d["id"] == "test_789"
        assert d["task"] == "Test task"
        assert d["status"] == "completed"
        assert d["result"] == "Done"


# SubagentConfig Tests


class TestSubagentConfig:
    """Tests for SubagentConfig."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = SubagentConfig()

        assert config.max_turns == 10
        assert config.timeout == 300.0

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = SubagentConfig(
            model={"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
            max_turns=5,
            timeout=60.0,
        )

        assert config.model["provider"] == "anthropic"
        assert config.max_turns == 5
        assert config.timeout == 60.0


# SubagentSpawner Tests


class TestSubagentSpawner:
    """Tests for SubagentSpawner."""

    def test_init(self) -> None:
        """Test spawner initialization."""
        spawner = SubagentSpawner(max_concurrent=3)

        assert spawner.active_count == 0
        assert spawner._max_concurrent == 3

    def test_generate_id(self) -> None:
        """Test ID generation."""
        spawner = SubagentSpawner()

        id1 = spawner._generate_id()
        id2 = spawner._generate_id()

        assert id1.startswith("subagent_")
        assert id2.startswith("subagent_")
        assert id1 != id2

    @pytest.mark.asyncio
    async def test_spawn_creates_task(self) -> None:
        """Test that spawn creates a task."""
        spawner = SubagentSpawner()

        with patch.object(spawner, "_run_subagent", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = SubagentResult(
                id="test",
                task="Test task",
                status=SubagentStatus.COMPLETED,
                result="Done",
            )

            subagent_id = await spawner.spawn("Test task")

            assert subagent_id.startswith("subagent_")
            assert spawner.active_count == 1 or subagent_id in spawner._results

    def test_get_status_unknown(self) -> None:
        """Test getting status of unknown subagent."""
        spawner = SubagentSpawner()

        status = spawner.get_status("unknown_id")
        assert status is None

    def test_list_subagents_empty(self) -> None:
        """Test listing subagents when empty."""
        spawner = SubagentSpawner()

        subagents = spawner.list_subagents()
        assert subagents == []

    def test_clear_results(self) -> None:
        """Test clearing results."""
        spawner = SubagentSpawner()

        # Add a mock result
        spawner._results["test_id"] = SubagentResult(
            id="test_id",
            task="Test",
            status=SubagentStatus.COMPLETED,
        )

        count = spawner.clear_results()

        assert count == 1
        assert len(spawner._results) == 0

    @pytest.mark.asyncio
    async def test_cancel_returns_false_for_unknown(self) -> None:
        """Test cancelling unknown subagent."""
        spawner = SubagentSpawner()

        result = spawner.cancel("unknown_id")
        assert result is False


# SubagentsMiddleware Tests


class TestSubagentsMiddleware:
    """Tests for SubagentsMiddleware."""

    def test_init(self) -> None:
        """Test middleware initialization."""
        middleware = SubagentsMiddleware(
            max_concurrent=3,
            max_turns=5,
            timeout=60.0,
        )

        assert middleware._max_concurrent == 3
        assert middleware._default_config.max_turns == 5
        assert middleware._default_config.timeout == 60.0

    def test_get_tools(self) -> None:
        """Test that middleware returns expected tools."""
        middleware = SubagentsMiddleware()
        tools = middleware.get_tools()
        tool_names = [t.name for t in tools]

        assert "spawn_subagent" in tool_names
        assert "spawn_parallel" in tool_names
        assert "wait_subagent" in tool_names
        assert "wait_all_subagents" in tool_names
        assert "get_subagent_result" in tool_names
        assert "list_subagents" in tool_names
        assert "cancel_subagent" in tool_names

    def test_tool_categories(self) -> None:
        """Test that tools have correct categories."""
        middleware = SubagentsMiddleware()
        tools = middleware.get_tools()

        for tool in tools:
            assert tool.category == "subagents"

    def test_system_prompt_segment(self) -> None:
        """Test system prompt content."""
        middleware = SubagentsMiddleware(max_concurrent=5)
        segment = middleware.get_system_prompt_segment()

        assert "Parallel Subagents" in segment
        assert "spawn_subagent" in segment
        assert "Max concurrent: 5" in segment

    @pytest.mark.asyncio
    async def test_spawn_subagent(self) -> None:
        """Test spawning subagent via middleware."""
        middleware = SubagentsMiddleware()

        with patch.object(
            middleware._spawner, "spawn", new_callable=AsyncMock
        ) as mock_spawn:
            mock_spawn.return_value = "subagent_test123"

            result = await middleware._spawn_subagent("Research task")

            assert result["status"] == "spawned"
            assert result["id"] == "subagent_test123"
            mock_spawn.assert_called_once()

    @pytest.mark.asyncio
    async def test_spawn_parallel_limit(self) -> None:
        """Test parallel spawning respects limits."""
        middleware = SubagentsMiddleware(max_concurrent=2)

        result = await middleware._spawn_parallel(
            ["Task 1", "Task 2", "Task 3", "Task 4"]
        )

        assert "error" in result
        assert "Too many tasks" in result["error"]

    @pytest.mark.asyncio
    async def test_spawn_parallel_success(self) -> None:
        """Test successful parallel spawning."""
        middleware = SubagentsMiddleware(max_concurrent=5)

        with patch.object(
            middleware._spawner, "spawn_many", new_callable=AsyncMock
        ) as mock_spawn:
            mock_spawn.return_value = ["id1", "id2", "id3"]

            result = await middleware._spawn_parallel(
                ["Task 1", "Task 2", "Task 3"]
            )

            assert result["status"] == "spawned"
            assert result["count"] == 3

    @pytest.mark.asyncio
    async def test_wait_subagent(self) -> None:
        """Test waiting for subagent."""
        middleware = SubagentsMiddleware()

        mock_result = SubagentResult(
            id="test_id",
            task="Test task",
            status=SubagentStatus.COMPLETED,
            result="Done",
        )

        with patch.object(
            middleware._spawner, "wait", new_callable=AsyncMock
        ) as mock_wait:
            mock_wait.return_value = mock_result

            result = await middleware._wait_subagent("test_id")

            assert result["status"] == "completed"
            assert result["result"] == "Done"

    @pytest.mark.asyncio
    async def test_wait_subagent_error(self) -> None:
        """Test waiting for unknown subagent."""
        middleware = SubagentsMiddleware()

        with patch.object(
            middleware._spawner, "wait", new_callable=AsyncMock
        ) as mock_wait:
            mock_wait.side_effect = ValueError("Unknown subagent")

            result = await middleware._wait_subagent("unknown_id")

            assert "error" in result

    @pytest.mark.asyncio
    async def test_wait_all(self) -> None:
        """Test waiting for all subagents."""
        middleware = SubagentsMiddleware()

        mock_results = [
            SubagentResult(id="id1", task="Task 1", status=SubagentStatus.COMPLETED),
            SubagentResult(id="id2", task="Task 2", status=SubagentStatus.COMPLETED),
        ]

        with patch.object(
            middleware._spawner, "wait_all", new_callable=AsyncMock
        ) as mock_wait:
            mock_wait.return_value = mock_results

            result = await middleware._wait_all()

            assert result["count"] == 2

    def test_get_result_not_found(self) -> None:
        """Test getting result for unknown subagent."""
        middleware = SubagentsMiddleware()

        result = middleware._get_result("unknown_id")

        assert "error" in result

    def test_get_result_running(self) -> None:
        """Test getting result for running subagent."""
        middleware = SubagentsMiddleware()

        with patch.object(
            middleware._spawner, "get_result"
        ) as mock_get:
            mock_get.return_value = None

            with patch.object(
                middleware._spawner, "get_status"
            ) as mock_status:
                mock_status.return_value = SubagentStatus.RUNNING

                result = middleware._get_result("running_id")

                assert result["status"] == "running"
                assert "still running" in result["message"]

    def test_list_subagents(self) -> None:
        """Test listing subagents."""
        middleware = SubagentsMiddleware()

        with patch.object(middleware._spawner, "list_subagents") as mock_list:
            mock_list.return_value = [
                {"id": "id1", "status": "running"},
                {"id": "id2", "status": "completed"},
            ]

            result = middleware._list_subagents()

            assert result["total"] == 2
            assert result["active"] == 1

    def test_cancel_subagent(self) -> None:
        """Test cancelling subagent."""
        middleware = SubagentsMiddleware()

        with patch.object(middleware._spawner, "cancel") as mock_cancel:
            mock_cancel.return_value = True

            result = middleware._cancel_subagent("test_id")

            assert result["status"] == "cancelled"

    def test_cancel_subagent_not_found(self) -> None:
        """Test cancelling unknown subagent."""
        middleware = SubagentsMiddleware()

        with patch.object(middleware._spawner, "cancel") as mock_cancel:
            mock_cancel.return_value = False

            result = middleware._cancel_subagent("unknown_id")

            assert "error" in result

    def test_state_persistence(self) -> None:
        """Test middleware state persistence."""
        middleware = SubagentsMiddleware(max_concurrent=3)
        state = middleware.get_state()

        assert state["max_concurrent"] == 3
        assert "active_count" in state


# Integration-style Tests (with mocks)


class TestSubagentsIntegration:
    """Integration tests for subagents system."""

    @pytest.mark.asyncio
    async def test_research_workflow(self) -> None:
        """Test a typical research workflow with subagents."""
        middleware = SubagentsMiddleware(max_concurrent=3)

        # Mock the spawner methods
        with patch.object(
            middleware._spawner, "spawn_many", new_callable=AsyncMock
        ) as mock_spawn:
            mock_spawn.return_value = ["id1", "id2", "id3"]

            # Spawn parallel research tasks
            spawn_result = await middleware._spawn_parallel([
                "Research topic A",
                "Research topic B",
                "Research topic C",
            ])

            assert spawn_result["status"] == "spawned"
            assert spawn_result["count"] == 3

        # Mock wait_all to return results
        with patch.object(
            middleware._spawner, "wait_all", new_callable=AsyncMock
        ) as mock_wait:
            mock_wait.return_value = [
                SubagentResult(
                    id="id1",
                    task="Research topic A",
                    status=SubagentStatus.COMPLETED,
                    result="Findings for A",
                ),
                SubagentResult(
                    id="id2",
                    task="Research topic B",
                    status=SubagentStatus.COMPLETED,
                    result="Findings for B",
                ),
                SubagentResult(
                    id="id3",
                    task="Research topic C",
                    status=SubagentStatus.COMPLETED,
                    result="Findings for C",
                ),
            ]

            # Wait for all results
            results = await middleware._wait_all()

            assert results["count"] == 3
            assert all(r["status"] == "completed" for r in results["results"])

    @pytest.mark.asyncio
    async def test_error_handling_workflow(self) -> None:
        """Test handling errors in subagent workflow."""
        middleware = SubagentsMiddleware()

        # Test spawning with error
        with patch.object(
            middleware._spawner, "spawn", new_callable=AsyncMock
        ) as mock_spawn:
            mock_spawn.side_effect = Exception("Spawn failed")

            result = await middleware._spawn_subagent("Failing task")

            assert "error" in result

        # Test waiting with timeout result
        with patch.object(
            middleware._spawner, "wait", new_callable=AsyncMock
        ) as mock_wait:
            mock_wait.return_value = SubagentResult(
                id="timeout_id",
                task="Timeout task",
                status=SubagentStatus.FAILED,
                error="Subagent timed out after 300s",
            )

            result = await middleware._wait_subagent("timeout_id")

            assert result["status"] == "failed"
            assert "timed out" in result["error"]
