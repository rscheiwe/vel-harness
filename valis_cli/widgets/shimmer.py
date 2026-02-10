"""
Shimmer Text Widget

Terminal shimmer effect - moving brightness gradient across text.
Mimics CSS background-position animation.
"""

import math
from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text


class TextShimmer(Widget):
    """
    Terminal shimmer effect - moving brightness gradient across text.
    """

    DEFAULT_CSS = """
    TextShimmer {
        height: auto;
        width: auto;
    }
    """

    position = reactive(0.0)  # 0.0 to 1.0

    def __init__(
        self,
        text: str = "",
        duration: float = 2.0,       # seconds for full cycle
        spread: float = 0.15,        # width of bright region (0-1)
        base_color: tuple = (100, 100, 100),      # RGB muted
        shimmer_color: tuple = (255, 255, 255),   # RGB bright
        **kwargs
    ):
        super().__init__(**kwargs)
        self._text = text
        self.duration = duration
        self.spread = spread
        self.base_color = base_color
        self.shimmer_color = shimmer_color
        self._running = False

    def on_mount(self) -> None:
        """Start the shimmer animation."""
        self.start()

    def start(self) -> None:
        """Start the shimmer animation."""
        if not self._running:
            self._running = True
            fps = 30
            self.set_interval(1 / fps, self._tick, name="shimmer_tick")

    def stop(self) -> None:
        """Stop the shimmer animation."""
        self._running = False
        # Timer will be cleaned up automatically

    def _tick(self) -> None:
        """Update shimmer position each frame."""
        if not self._running:
            return
        # Move position from 1.0 → 0.0 (right to left)
        step = 1 / (self.duration * 30)
        self.position = (self.position - step) % 1.0

    def watch_position(self, _: float) -> None:
        """Refresh when position changes."""
        self.refresh()

    def render(self) -> Text:
        """Render the shimmering text."""
        text = Text()
        length = len(self._text)

        if length == 0:
            return text

        for i, char in enumerate(self._text):
            # Normalize character position to 0-1
            char_pos = i / max(length - 1, 1)

            # Distance from shimmer center (accounting for spread)
            shimmer_center = self.position * (1 + self.spread * 2) - self.spread
            distance = abs(char_pos - shimmer_center)

            # Calculate intensity (1.0 at center, 0.0 outside spread)
            if distance < self.spread:
                # Smooth falloff using cosine
                intensity = (1 + math.cos(math.pi * distance / self.spread)) / 2
            else:
                intensity = 0.0

            # Blend colors
            r = int(self.base_color[0] + (self.shimmer_color[0] - self.base_color[0]) * intensity)
            g = int(self.base_color[1] + (self.shimmer_color[1] - self.base_color[1]) * intensity)
            b = int(self.base_color[2] + (self.shimmer_color[2] - self.base_color[2]) * intensity)

            text.append(char, style=f"rgb({r},{g},{b})")

        return text

    def update_text(self, new_text: str) -> None:
        """Update the displayed text."""
        self._text = new_text
        self.refresh()
