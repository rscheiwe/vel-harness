"""
Tests for Retry Middleware
"""

import asyncio
import time
import pytest
from unittest.mock import MagicMock

from vel import ToolSpec

from vel_harness.middleware.retry import (
    RetryConfig,
    RetryAttempt,
    RetryResult,
    ToolRetryMiddleware,
    CircuitBreaker,
    CircuitBreakerMiddleware,
    create_retry_middleware,
)


class TestRetryConfig:
    """Test RetryConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = RetryConfig()
        assert config.max_retries == 2
        assert config.backoff_base == 1.0
        assert config.backoff_multiplier == 2.0
        assert "write_file" in config.no_retry_tools
        assert "web_search" in config.always_retry_tools

    def test_custom_values(self):
        """Test custom configuration values."""
        config = RetryConfig(
            max_retries=5,
            backoff_base=0.5,
            backoff_multiplier=3.0,
        )
        assert config.max_retries == 5
        assert config.backoff_base == 0.5
        assert config.backoff_multiplier == 3.0


class TestRetryResult:
    """Test RetryResult dataclass."""

    def test_success_result(self):
        """Test successful result."""
        result = RetryResult(
            success=True,
            result={"data": "value"},
            attempts=1,
            total_time=0.5,
            retry_history=[],
        )
        assert result.success
        assert result.attempts == 1

    def test_failure_result(self):
        """Test failure result with retry history."""
        result = RetryResult(
            success=False,
            result=ValueError("error"),
            attempts=3,
            total_time=5.0,
            retry_history=[
                RetryAttempt(attempt=1, error="first error", delay=1.0, timestamp=0),
                RetryAttempt(attempt=2, error="second error", delay=2.0, timestamp=1),
            ],
        )
        assert not result.success
        assert result.attempts == 3
        assert len(result.retry_history) == 2


class TestToolRetryMiddleware:
    """Test ToolRetryMiddleware class."""

    @pytest.fixture
    def middleware(self):
        """Create retry middleware."""
        config = RetryConfig(
            max_retries=3,
            backoff_base=0.01,  # Fast for testing
            backoff_multiplier=2.0,
        )
        return ToolRetryMiddleware(config=config)

    def test_should_retry_under_limit(self, middleware):
        """Test should retry when under attempt limit."""
        assert middleware.should_retry("read_file", Exception("error"), 1)
        assert middleware.should_retry("read_file", Exception("error"), 2)

    def test_should_not_retry_at_limit(self, middleware):
        """Test should not retry when at limit."""
        assert not middleware.should_retry("read_file", Exception("error"), 3)

    def test_should_not_retry_excluded_tool(self, middleware):
        """Test should not retry excluded tools."""
        assert not middleware.should_retry("write_file", Exception("error"), 1)
        assert not middleware.should_retry("execute", Exception("error"), 1)

    def test_should_retry_always_retry_tools(self, middleware):
        """Test always retry tools are retried."""
        assert middleware.should_retry("web_search", Exception("error"), 1)

    def test_should_not_retry_never_retry_exceptions(self, middleware):
        """Test never-retry exceptions are not retried."""
        assert not middleware.should_retry("read_file", ValueError("error"), 1)
        assert not middleware.should_retry("read_file", TypeError("error"), 1)

    def test_get_delay_exponential(self, middleware):
        """Test exponential backoff delays."""
        delay1 = middleware.get_delay(1)
        delay2 = middleware.get_delay(2)
        delay3 = middleware.get_delay(3)

        # Each should be roughly double the previous (with jitter)
        assert delay2 > delay1
        assert delay3 > delay2

    def test_get_delay_max_cap(self):
        """Test delay is capped at max_delay."""
        config = RetryConfig(
            backoff_base=10.0,
            backoff_multiplier=10.0,
            max_delay=5.0,
        )
        middleware = ToolRetryMiddleware(config=config)

        delay = middleware.get_delay(5)
        assert delay <= 5.0 * 1.2  # Max delay + jitter

    def test_execute_with_retry_success_first_try(self, middleware):
        """Test successful execution on first try."""
        def handler():
            return "success"

        result = middleware.execute_with_retry(handler, "test_tool", {})

        assert result.success
        assert result.result == "success"
        assert result.attempts == 1
        assert len(result.retry_history) == 0

    def test_execute_with_retry_success_after_retries(self, middleware):
        """Test successful execution after retries."""
        call_count = 0

        def handler():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("temporary error")
            return "success"

        result = middleware.execute_with_retry(handler, "test_tool", {})

        assert result.success
        assert result.result == "success"
        assert result.attempts == 3
        assert len(result.retry_history) == 2

    def test_execute_with_retry_failure(self, middleware):
        """Test failure after all retries exhausted."""
        def handler():
            raise RuntimeError("persistent error")

        result = middleware.execute_with_retry(handler, "test_tool", {})

        assert not result.success
        assert isinstance(result.result, RuntimeError)

    @pytest.mark.asyncio
    async def test_wrap_tool(self, middleware):
        """Test wrapping a tool with retry logic."""
        call_count = 0

        def handler():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("error")
            return "success"

        tool = ToolSpec.from_function(
            handler,
            name="test_tool",
            description="Test tool",
        )

        wrapped = middleware.wrap_tool(tool)
        result = await wrapped._handler()

        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_wrap_tool_failure_raises(self, middleware):
        """Test wrapped tool raises on final failure."""
        def handler():
            raise RuntimeError("always fails")

        tool = ToolSpec.from_function(
            handler,
            name="test_tool",
            description="Test tool",
        )

        wrapped = middleware.wrap_tool(tool)

        with pytest.raises(RuntimeError, match="always fails"):
            await wrapped._handler()


class TestToolRetryMiddlewareAsync:
    """Test async retry functionality."""

    @pytest.fixture
    def middleware(self):
        """Create retry middleware with fast backoff."""
        config = RetryConfig(
            max_retries=3,
            backoff_base=0.01,
        )
        return ToolRetryMiddleware(config=config)

    @pytest.mark.asyncio
    async def test_execute_async_success(self, middleware):
        """Test async execution success."""
        async def handler():
            return "async success"

        result = await middleware.execute_with_retry_async(
            handler, "test_tool", {}
        )

        assert result.success
        assert result.result == "async success"

    @pytest.mark.asyncio
    async def test_execute_async_with_retries(self, middleware):
        """Test async execution with retries."""
        call_count = 0

        async def handler():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("error")
            return "success"

        result = await middleware.execute_with_retry_async(
            handler, "test_tool", {}
        )

        assert result.success
        assert call_count == 3


class TestCircuitBreaker:
    """Test CircuitBreaker class."""

    @pytest.fixture
    def breaker(self):
        """Create a circuit breaker."""
        return CircuitBreaker(failure_threshold=3, reset_timeout=0.1)

    def test_initial_state_closed(self, breaker):
        """Test initial state is closed."""
        assert not breaker.is_open

    def test_opens_after_threshold(self, breaker):
        """Test circuit opens after failure threshold."""
        breaker.record_failure()
        breaker.record_failure()
        assert not breaker.is_open

        breaker.record_failure()
        assert breaker.is_open

    def test_success_resets_count(self, breaker):
        """Test success resets failure count."""
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_success()

        assert breaker._failure_count == 0
        assert not breaker.is_open

    def test_resets_after_timeout(self, breaker):
        """Test circuit resets after timeout."""
        for _ in range(3):
            breaker.record_failure()

        assert breaker.is_open

        # Wait for reset timeout
        time.sleep(0.15)

        assert not breaker.is_open

    def test_get_state(self, breaker):
        """Test getting circuit state."""
        state = breaker.get_state()

        assert "is_open" in state
        assert "failure_count" in state
        assert "failure_threshold" in state


class TestCircuitBreakerMiddleware:
    """Test CircuitBreakerMiddleware class."""

    @pytest.fixture
    def middleware(self):
        """Create circuit breaker middleware."""
        return CircuitBreakerMiddleware(
            failure_threshold=2,
            reset_timeout=0.1,
        )

    @pytest.mark.asyncio
    async def test_wrap_tool_success(self, middleware):
        """Test wrapped tool works on success."""
        def handler():
            return "success"

        tool = ToolSpec.from_function(
            handler,
            name="test_tool",
            description="Test",
        )

        wrapped = middleware.wrap_tool(tool)
        result = await wrapped._handler()

        assert result == "success"

    @pytest.mark.asyncio
    async def test_wrap_tool_opens_on_failures(self, middleware):
        """Test wrapped tool opens circuit on failures."""
        def handler():
            raise RuntimeError("error")

        tool = ToolSpec.from_function(
            handler,
            name="test_tool",
            description="Test",
        )

        wrapped = middleware.wrap_tool(tool)

        # First failure
        with pytest.raises(RuntimeError):
            await wrapped._handler()

        # Second failure - opens circuit
        with pytest.raises(RuntimeError):
            await wrapped._handler()

        # Third call - circuit open
        with pytest.raises(RuntimeError, match="Circuit breaker open"):
            await wrapped._handler()

    def test_get_stats(self, middleware):
        """Test getting circuit statistics."""
        stats = middleware.get_stats()

        assert "circuits" in stats
        assert "failure_threshold" in stats
        assert "reset_timeout" in stats


class TestCreateRetryMiddleware:
    """Test create_retry_middleware factory."""

    def test_create_simple(self):
        """Test creating simple retry middleware."""
        middleware = create_retry_middleware()
        assert isinstance(middleware, ToolRetryMiddleware)

    def test_create_with_circuit_breaker(self):
        """Test creating with circuit breaker."""
        retry_mw, circuit_mw = create_retry_middleware(use_circuit_breaker=True)

        assert isinstance(retry_mw, ToolRetryMiddleware)
        assert isinstance(circuit_mw, CircuitBreakerMiddleware)

    def test_create_with_custom_settings(self):
        """Test creating with custom settings."""
        middleware = create_retry_middleware(
            max_retries=5,
            backoff_base=0.5,
        )

        assert middleware.config.max_retries == 5
        assert middleware.config.backoff_base == 0.5


class TestRetryIntegration:
    """Integration tests for retry middleware."""

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test full retry workflow."""
        middleware = create_retry_middleware(
            max_retries=3,
            backoff_base=0.01,
        )

        attempt_count = 0

        def flaky_handler(value: int) -> int:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise RuntimeError("temporary failure")
            return value * 2

        tool = ToolSpec.from_function(
            flaky_handler,
            name="flaky_tool",
            description="A flaky tool",
        )

        wrapped = middleware.wrap_tool(tool)
        result = await wrapped._handler(value=5)

        assert result == 10
        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_retry_with_circuit_breaker(self):
        """Test retry and circuit breaker together."""
        retry_mw, circuit_mw = create_retry_middleware(
            max_retries=1,
            backoff_base=0.01,
            use_circuit_breaker=True,
            circuit_failure_threshold=2,
        )

        def always_fails():
            raise RuntimeError("always fails")

        tool = ToolSpec.from_function(
            always_fails,
            name="bad_tool",
            description="Always fails",
        )

        # Wrap with both middlewares
        wrapped = circuit_mw.wrap_tool(retry_mw.wrap_tool(tool))

        # First call fails (with retries)
        with pytest.raises(RuntimeError):
            await wrapped._handler()

        # Second call fails and opens circuit
        with pytest.raises(RuntimeError):
            await wrapped._handler()

        # Third call blocked by circuit
        with pytest.raises(RuntimeError, match="Circuit breaker open"):
            await wrapped._handler()
