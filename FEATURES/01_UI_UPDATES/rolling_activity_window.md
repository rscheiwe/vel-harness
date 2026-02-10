**Rolling Activity Window**

```
┌─────────────────────────────────────────────────────────────────┐
│ ● Explore(Explore ctx-zip-py project)                          │  ← Header: agent name + task
│   ├─ Waiting…-la /Users/richard.s/ctx-zip-proj/...             │  ← Slot 1: 2nd most recent
│   │  Waiting…d /Users/richard.s/ctx-zip-proj/... | sort)       │  ← Slot 2: most recent  
│   └─ +5 more tool uses (ctrl+o to expand)                      │  ← Counter: hidden activity
└─────────────────────────────────────────────────────────────────┘
```

**Behavior:**

| Event | What happens |
|-------|--------------|
| New tool call | Slot 1 → discarded, Slot 2 → Slot 1, New → Slot 2 |
| Counter | Increments with each discarded row |
| `ctrl+o` | Expands to show full history |

**Implementation spec:**

```python
class RollingActivityWindow:
    """Space-efficient subagent activity display.
    
    Shows last N tool calls in fixed-height window.
    Older calls roll off top, counter tracks hidden activity.
    """
    
    def __init__(
        self,
        visible_slots: int = 2,       # Number of visible recent actions
        truncate_width: int = 60,     # Truncate long commands
        prefix: str = "Waiting…",     # Shown while tool is pending
    ):
        self.visible_slots = visible_slots
        self.truncate_width = truncate_width
        self.prefix = prefix
        self.history: list[str] = []
        self.hidden_count: int = 0
    
    def push(self, tool_description: str):
        """Add new tool call, roll window up."""
        if len(self.history) >= self.visible_slots:
            self.hidden_count += 1
            self.history.pop(0)  # Remove oldest visible
        self.history.append(tool_description)
        self.render()
    
    def render(self):
        """Render the fixed-height window."""
        # Header
        print(f"● {self.agent_name}({self.task_summary})")
        
        # Activity slots (tree-style indent)
        for i, item in enumerate(self.history):
            prefix = "├─" if i < len(self.history) - 1 else "└─"
            truncated = self._truncate(item)
            print(f"  {prefix} {self.prefix}{truncated}")
        
        # Hidden counter
        if self.hidden_count > 0:
            print(f"  +{self.hidden_count} more tool uses (ctrl+o to expand)")
    
    def _truncate(self, text: str) -> str:
        if len(text) > self.truncate_width:
            return text[:self.truncate_width] + "..."
        return text
```

**Key UX details:**

1. **Fixed height** - Window never grows, prevents terminal scroll spam
2. **LIFO visible** - Most recent always visible at bottom
3. **Truncated paths** - Long paths cut with `…` (not `...`)
4. **Pending indicator** - "Waiting…" prefix while tool runs, replaced with result on completion
5. **Expandable** - `ctrl+o` reveals full history if user wants it
6. **Tree indent** - `├─` / `└─` shows hierarchy under agent header