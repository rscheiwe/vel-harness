"""
Middleware Base Protocol

Defines the interface that all middleware components must implement.
"""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class Middleware(Protocol):
    """
    Protocol for middleware components.

    Middleware provides:
    - Tools: Functions the agent can call
    - System prompt segments: Instructions added to the agent's prompt
    - State management: Persistence and restoration of middleware state
    """

    def get_tools(self) -> List[Any]:
        """
        Return tools provided by this middleware.

        Returns:
            List of ToolSpec instances
        """
        ...

    def get_system_prompt_segment(self) -> str:
        """
        Return system prompt segment for this middleware.

        Returns:
            Markdown-formatted string to append to system prompt
        """
        ...

    def get_state(self) -> Dict[str, Any]:
        """
        Get current middleware state for persistence.

        Returns:
            Dict representing serializable state
        """
        ...

    def load_state(self, state: Dict[str, Any]) -> None:
        """
        Load middleware state from persistence.

        Args:
            state: Previously saved state dict
        """
        ...


class BaseMiddleware:
    """
    Base class for middleware implementations.

    Provides default implementations for optional methods.
    """

    def get_tools(self) -> List[Any]:
        """Return empty list by default."""
        return []

    def get_system_prompt_segment(self) -> str:
        """Return empty string by default."""
        return ""

    def get_state(self) -> Dict[str, Any]:
        """Return empty state by default."""
        return {}

    def load_state(self, state: Dict[str, Any]) -> None:
        """No-op by default."""
        pass
