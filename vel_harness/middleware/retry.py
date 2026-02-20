"""
Retry Middleware

Automatically retry failed tool calls with configurable backoff.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type, Union

from vel import ToolSpec


logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    # Retry settings
    max_retries: int = 2
    backoff_base: float = 1.0  # Base delay in seconds
    backoff_multiplier: float = 2.0  # Exponential multiplier
    max_delay: float = 30.0  # Maximum delay between retries

    # Which exceptions to retry on
    retry_on: Tuple[Type[Exception], ...] = field(
        default_factory=lambda: (
            Exception,  # Retry all by default
        )
    )

    # Exceptions to never retry
    never_retry: Set[str] = field(
        default_factory=lambda: {
            "ValueError",
            "TypeError",
            "KeyError",
            "AttributeError",
        }
    )

    # Tools that should not be retried
    no_retry_tools: Set[str] = field(
        default_factory=lambda: {
            "write_file",  # Don't retry writes
            "edit_file",
            "delete_file",
            "execute",  # Don't retry execution
            "run_command",
        }
    )

    # Tools that should always be retried
    always_retry_tools: Set[str] = field(
        default_factory=lambda: {
            "web_search",
            "web_fetch",
            "execute_sql",
        }
    )


@dataclass
class RetryAttempt:
    """Record of a retry attempt."""

    attempt: int
    error: str
    delay: float
    timestamp: float


@dataclass
class RetryResult:
    """Result of a retried operation."""

    success: bool
    result: Optional[Any]
    attempts: int
    total_time: float
    retry_history: List[RetryAttempt]


class ToolRetryMiddleware:
    """
    Automatically retry failed tool calls.

    Implements exponential backoff and configurable retry policies.
    """

    def __init__(
        self,
        config: Optional[RetryConfig] = None,
    ):
        self.config = config or RetryConfig()
        self._retry_history: Dict[str, List[RetryAttempt]] = {}

    def should_retry(
        self,
        tool_name: str,
        error: Exception,
        attempt: int,
    ) -> bool:
        """
        Determine if an operation should be retried.

        Args:
            tool_name: Name of the tool
            error: The exception that occurred
            attempt: Current attempt number (1-indexed)

        Returns:
            True if operation should be retried
        """
        # Check attempt limit
        if attempt >= self.config.max_retries:
            return False

        # Check tool exclusions
        if tool_name in self.config.no_retry_tools:
            return False

        # Check always-retry tools
        if tool_name in self.config.always_retry_tools:
            return True

        # Check exception type
        error_type = type(error).__name__
        if error_type in self.config.never_retry:
            return False

        # Check if error matches retry_on types
        return isinstance(error, self.config.retry_on)

    def get_delay(self, attempt: int) -> float:
        """
        Calculate delay before next retry.

        Uses exponential backoff with jitter.

        Args:
            attempt: Current attempt number

        Returns:
            Delay in seconds
        """
        import random

        base_delay = self.config.backoff_base * (
            self.config.backoff_multiplier ** (attempt - 1)
        )

        # Add jitter (10-20% random variation)
        jitter = base_delay * random.uniform(0.1, 0.2)

        delay = min(base_delay + jitter, self.config.max_delay)
        return delay

    def execute_with_retry(
        self,
        handler: Callable[..., Any],
        tool_name: str,
        args: Dict[str, Any],
    ) -> RetryResult:
        """
        Execute a tool handler with retry logic.

        Args:
            handler: The tool handler function
            tool_name: Name of the tool
            args: Arguments to pass to handler

        Returns:
            RetryResult with outcome
        """
        start_time = time.time()
        retry_history: List[RetryAttempt] = []
        last_error: Optional[Exception] = None

        for attempt in range(1, self.config.max_retries + 2):
            try:
                result = handler(**args)
                return RetryResult(
                    success=True,
                    result=result,
                    attempts=attempt,
                    total_time=time.time() - start_time,
                    retry_history=retry_history,
                )
            except Exception as e:
                last_error = e
                logger.debug(
                    f"Tool {tool_name} failed on attempt {attempt}: {e}"
                )

                if not self.should_retry(tool_name, e, attempt):
                    break

                delay = self.get_delay(attempt)
                retry_history.append(RetryAttempt(
                    attempt=attempt,
                    error=str(e),
                    delay=delay,
                    timestamp=time.time(),
                ))

                time.sleep(delay)

        return RetryResult(
            success=False,
            result=last_error,
            attempts=len(retry_history) + 1,
            total_time=time.time() - start_time,
            retry_history=retry_history,
        )

    async def execute_with_retry_async(
        self,
        handler: Callable[..., Any],
        tool_name: str,
        args: Dict[str, Any],
    ) -> RetryResult:
        """
        Execute a tool handler with retry logic (async version).

        Args:
            handler: The tool handler function (sync or async)
            tool_name: Name of the tool
            args: Arguments to pass to handler

        Returns:
            RetryResult with outcome
        """
        start_time = time.time()
        retry_history: List[RetryAttempt] = []
        last_error: Optional[Exception] = None

        for attempt in range(1, self.config.max_retries + 2):
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(**args)
                else:
                    result = handler(**args)
                return RetryResult(
                    success=True,
                    result=result,
                    attempts=attempt,
                    total_time=time.time() - start_time,
                    retry_history=retry_history,
                )
            except Exception as e:
                last_error = e
                logger.debug(
                    f"Tool {tool_name} failed on attempt {attempt}: {e}"
                )

                if not self.should_retry(tool_name, e, attempt):
                    break

                delay = self.get_delay(attempt)
                retry_history.append(RetryAttempt(
                    attempt=attempt,
                    error=str(e),
                    delay=delay,
                    timestamp=time.time(),
                ))

                await asyncio.sleep(delay)

        return RetryResult(
            success=False,
            result=last_error,
            attempts=len(retry_history) + 1,
            total_time=time.time() - start_time,
            retry_history=retry_history,
        )

    def wrap_tool(self, tool: ToolSpec) -> ToolSpec:
        """
        Wrap a tool with retry behavior.

        Args:
            tool: Original tool spec

        Returns:
            Wrapped tool with retry logic
        """
        middleware = self
        original_handler = tool._handler

        async def retry_handler(**kwargs: Any) -> Any:
            result = await middleware.execute_with_retry_async(
                original_handler, tool.name, kwargs
            )

            if result.success:
                return result.result
            else:
                # Re-raise the last error
                if isinstance(result.result, Exception):
                    raise result.result
                raise RuntimeError(f"Tool {tool.name} failed after retries")

        return ToolSpec.from_function(
            retry_handler,
            name=tool.name,
            description=tool.description,
            category=tool.category,
            tags=tool.tags,
        )

    def get_system_prompt_segment(self) -> str:
        """System prompt segment about retry behavior."""
        return f"""
## Tool Retry

Failed tool calls are automatically retried up to {self.config.max_retries} times
with exponential backoff (starting at {self.config.backoff_base}s).

Tools excluded from retry: {', '.join(sorted(self.config.no_retry_tools))}
"""

    def get_stats(self) -> Dict[str, Any]:
        """Get retry statistics."""
        return {
            "max_retries": self.config.max_retries,
            "backoff_base": self.config.backoff_base,
            "backoff_multiplier": self.config.backoff_multiplier,
            "no_retry_tools": list(self.config.no_retry_tools),
            "always_retry_tools": list(self.config.always_retry_tools),
        }

    def get_tools(self) -> List[ToolSpec]:
        """Get retry management tools."""
        middleware = self

        def get_retry_config() -> Dict[str, Any]:
            """
            Get current retry configuration.

            Returns retry settings and statistics.
            """
            return middleware.get_stats()

        return [
            ToolSpec.from_function(
                get_retry_config,
                name="get_retry_config",
                description="Get current retry configuration and settings",
                category="system",
                tags=["retry", "config"],
            ),
        ]

    def get_state(self) -> Dict[str, Any]:
        """Get serializable state."""
        return {"stats": self.get_stats()}

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load state (no-op for retry)."""
        pass


class CircuitBreaker:
    """
    Circuit breaker to prevent repeated failures.

    Opens circuit after consecutive failures, preventing
    further calls until a timeout period passes.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
    ):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._is_open = False

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking calls)."""
        if self._is_open and self._last_failure_time:
            # Check if timeout has passed
            if time.time() - self._last_failure_time >= self.reset_timeout:
                self._is_open = False
                self._failure_count = 0
                return False
        return self._is_open

    def record_success(self) -> None:
        """Record a successful call."""
        self._failure_count = 0
        self._is_open = False

    def record_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._failure_count >= self.failure_threshold:
            self._is_open = True

    def get_state(self) -> Dict[str, Any]:
        """Get circuit breaker state."""
        return {
            "is_open": self.is_open,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "reset_timeout": self.reset_timeout,
        }


class CircuitBreakerMiddleware:
    """
    Middleware that applies circuit breaker pattern to tools.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
    ):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._circuits: Dict[str, CircuitBreaker] = {}

    def _get_circuit(self, tool_name: str) -> CircuitBreaker:
        """Get or create circuit breaker for a tool."""
        if tool_name not in self._circuits:
            self._circuits[tool_name] = CircuitBreaker(
                failure_threshold=self.failure_threshold,
                reset_timeout=self.reset_timeout,
            )
        return self._circuits[tool_name]

    def wrap_tool(self, tool: ToolSpec) -> ToolSpec:
        """Wrap a tool with circuit breaker."""
        middleware = self
        original_handler = tool._handler

        async def circuit_handler(**kwargs: Any) -> Any:
            circuit = middleware._get_circuit(tool.name)

            if circuit.is_open:
                raise RuntimeError(
                    f"Circuit breaker open for {tool.name}. "
                    f"Try again in {middleware.reset_timeout}s."
                )

            try:
                if asyncio.iscoroutinefunction(original_handler):
                    result = await original_handler(**kwargs)
                else:
                    result = original_handler(**kwargs)
                circuit.record_success()
                return result
            except Exception as e:
                circuit.record_failure()
                raise

        return ToolSpec.from_function(
            circuit_handler,
            name=tool.name,
            description=tool.description,
            category=tool.category,
            tags=tool.tags,
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "circuits": {
                name: circuit.get_state()
                for name, circuit in self._circuits.items()
            },
            "failure_threshold": self.failure_threshold,
            "reset_timeout": self.reset_timeout,
        }


def create_retry_middleware(
    max_retries: int = 2,
    backoff_base: float = 1.0,
    use_circuit_breaker: bool = False,
    circuit_failure_threshold: int = 5,
    circuit_reset_timeout: float = 60.0,
) -> Union[ToolRetryMiddleware, Tuple[ToolRetryMiddleware, CircuitBreakerMiddleware]]:
    """
    Create retry middleware with optional circuit breaker.

    Args:
        max_retries: Maximum retry attempts
        backoff_base: Base delay for exponential backoff
        use_circuit_breaker: Whether to include circuit breaker
        circuit_failure_threshold: Failures before circuit opens
        circuit_reset_timeout: Seconds before circuit resets

    Returns:
        ToolRetryMiddleware or tuple with CircuitBreakerMiddleware
    """
    config = RetryConfig(
        max_retries=max_retries,
        backoff_base=backoff_base,
    )
    retry_mw = ToolRetryMiddleware(config=config)

    if use_circuit_breaker:
        circuit_mw = CircuitBreakerMiddleware(
            failure_threshold=circuit_failure_threshold,
            reset_timeout=circuit_reset_timeout,
        )
        return retry_mw, circuit_mw

    return retry_mw
