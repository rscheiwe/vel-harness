"""
Vel Harness Fallback - Automatic model fallback on retryable errors.

Wraps DeepAgent's run/run_stream to automatically retry with a fallback
model when the primary model fails with retryable errors (rate limits,
server errors, overloaded).

Usage:
    from vel_harness.fallback import FallbackStreamWrapper

    wrapper = FallbackStreamWrapper(
        deep_agent=agent,
        fallback_model={"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
        max_retries=1,
    )

    async for event in wrapper.run_stream(input_text="Hello", session_id="123"):
        print(event)
"""

import logging
from typing import Any, AsyncIterator, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# HTTP status codes that trigger fallback
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 529}


class FallbackStreamWrapper:
    """Wraps a DeepAgent with automatic model fallback on error.

    When the primary model fails with a retryable error (rate limit,
    overloaded, server error), automatically switches to the fallback
    model and retries the request.

    The model switch is temporary per-request — the agent's model is
    restored after the fallback attempt completes.

    Args:
        deep_agent: The DeepAgent to wrap
        fallback_model: Model config dict for the fallback model
        max_retries: Maximum number of fallback retry attempts (default 1)
    """

    def __init__(
        self,
        deep_agent: Any,
        fallback_model: Dict[str, Any],
        max_retries: int = 1,
    ):
        self._agent = deep_agent
        self._fallback_model = fallback_model
        self._max_retries = max_retries

    @staticmethod
    def is_retryable_status(status_code: Optional[int]) -> bool:
        """Check if an HTTP status code is retryable.

        Args:
            status_code: HTTP status code from error event

        Returns:
            True if the error should trigger a fallback retry
        """
        if status_code is None:
            return False
        return status_code in RETRYABLE_STATUS_CODES

    @staticmethod
    def is_retryable_error(error_str: str) -> bool:
        """Check if an error message indicates a retryable error.

        Catches common retryable patterns even without a status code.

        Args:
            error_str: Error message string

        Returns:
            True if the error should trigger a fallback retry
        """
        retryable_patterns = [
            "rate limit",
            "rate_limit",
            "overloaded",
            "too many requests",
            "service unavailable",
            "internal server error",
            "bad gateway",
            "gateway timeout",
        ]
        error_lower = error_str.lower()
        return any(pattern in error_lower for pattern in retryable_patterns)

    async def run_stream(
        self,
        input_text: Union[str, List[Dict[str, Any]]],
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Run the agent with streaming, falling back on retryable errors.

        First attempts with the primary model. If a retryable error occurs,
        switches to the fallback model and retries.

        Args:
            input_text: User input
            session_id: Optional session ID
            context: Optional additional context

        Yields:
            Stream events from the agent
        """
        # Try primary model (buffer events so we can discard on retryable failure)
        error_event = None
        buffered_events: List[Any] = []
        async for event in self._agent.run_stream(
            input_text=input_text,
            session_id=session_id,
            context=context,
        ):
            if isinstance(event, dict) and event.get("type") == "error":
                status_code = event.get("status_code")
                error_str = event.get("error", "")

                if self.is_retryable_status(status_code) or self.is_retryable_error(error_str):
                    error_event = event
                    break
                else:
                    # Non-retryable error — flush buffer and pass through.
                    for buffered in buffered_events:
                        yield buffered
                    yield event
                    return
            else:
                buffered_events.append(event)

        # If no retryable error, flush primary buffer and exit.
        if error_event is None:
            for buffered in buffered_events:
                yield buffered
            return

        # Retry with fallback model
        for attempt in range(self._max_retries):
            logger.info(
                f"Fallback attempt {attempt + 1}/{self._max_retries}: "
                f"switching from {self._agent.agent.model_cfg.get('model', '?')} "
                f"to {self._fallback_model.get('model', '?')} "
                f"(error: {error_event.get('error', '?')[:100]})"
            )

            # Swap model temporarily
            original_model = self._agent.agent.model_cfg
            self._agent.agent.model_cfg = self._fallback_model

            try:
                fallback_error = None
                fallback_buffer: List[Any] = []
                async for event in self._agent.run_stream(
                    input_text=input_text,
                    session_id=session_id,
                    context=context,
                ):
                    if isinstance(event, dict) and event.get("type") == "error":
                        status_code = event.get("status_code")
                        error_str = event.get("error", "")

                        if self.is_retryable_status(status_code) or self.is_retryable_error(error_str):
                            fallback_error = event
                            break
                        else:
                            for buffered in fallback_buffer:
                                yield buffered
                            yield event
                            return
                    else:
                        fallback_buffer.append(event)

                if fallback_error is None:
                    # Fallback succeeded - emit buffered fallback stream.
                    for buffered in fallback_buffer:
                        yield buffered
                    return

                # Fallback also got retryable error — continue to next attempt
                error_event = fallback_error
            finally:
                # Restore original model
                self._agent.agent.model_cfg = original_model

        # All retries exhausted — yield the last error
        logger.warning(
            f"All {self._max_retries} fallback attempts exhausted. "
            f"Last error: {error_event.get('error', '?')[:200]}"
        )
        yield error_event

    async def run(
        self,
        input_text: Union[str, List[Dict[str, Any]]],
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Run the agent (non-streaming) with fallback.

        Collects all stream events and returns the final response.

        Args:
            input_text: User input
            session_id: Optional session ID
            context: Optional additional context

        Returns:
            Agent's response (or error dict if all retries fail)
        """
        last_event = None
        text_parts = []

        async for event in self.run_stream(
            input_text=input_text,
            session_id=session_id,
            context=context,
        ):
            last_event = event
            if isinstance(event, dict):
                if event.get("type") == "text-delta":
                    text_parts.append(event.get("delta", ""))
                elif event.get("type") == "error":
                    return event

        if text_parts:
            return {"content": "".join(text_parts)}
        return last_event
