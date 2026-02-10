**Tool Result Cards with Preview**

Two distinct card types:

---

**1. Write Card (File Creation)**

```
┌─────────────────────────────────────────────────────────────────┐
│ ● Write(valis_cli/commands/tokens.py)                          │  ← Header: tool + filepath
│   └─ Wrote 144 lines to valis_cli/commands/tokens.py           │  ← Summary line
│      """                                                        │
│      Tokens Command                                             │  ← Content preview
│      View token usage and context window statistics.            │     (syntax highlighted)
│      """                                                        │
│                                                                 │
│      from typing import Any, Dict                               │
│      from valis_cli.commands.base import Command, CommandResult │
│      … +134 lines (ctrl+o to expand)                           │  ← Collapse indicator
└─────────────────────────────────────────────────────────────────┘
```

---

**2. Update Card (File Edit/Diff)**

```
┌─────────────────────────────────────────────────────────────────┐
│ ● Update(valis_cli/commands/__init__.py)                       │  ← Header
│   └─ Updated valis_cli/commands/__init__.py with 1 addition    │  ← Summary (N additions/deletions)
│      16    from valis_cli.commands.reset import ResetCommand   │
│      17    from valis_cli.commands.skills import SkillInfo...  │  ← Context (unchanged)
│      18    from valis_cli.commands.permissions import Allow... │
│   19 +    from valis_cli.commands.tokens import TokensCommand  │  ← Added line (green +)
│      20                                                         │
│      21                                                         │  ← Context (unchanged)
│      22    def register_all_commands() -> None:                │
└─────────────────────────────────────────────────────────────────┘
```

---

**Implementation spec:**

```python
class ToolResultCard:
    """Collapsible tool result with preview."""
    
    @staticmethod
    def write_card(filepath: str, content: str, preview_lines: int = 8):
        """Display file creation result."""
        lines = content.splitlines()
        total = len(lines)
        
        print(f"● Write({filepath})")
        print(f"  └─ Wrote {total} lines to {filepath}")
        
        # Syntax-highlighted preview
        preview = lines[:preview_lines]
        for line in preview:
            print(f"     {syntax_highlight(line)}")
        
        # Collapse indicator if more content
        remaining = total - preview_lines
        if remaining > 0:
            print(f"     … +{remaining} lines (ctrl+o to expand)")
    
    @staticmethod
    def update_card(
        filepath: str,
        diff: list[DiffLine],
        context_lines: int = 3
    ):
        """Display file edit result with diff."""
        additions = sum(1 for d in diff if d.type == '+')
        deletions = sum(1 for d in diff if d.type == '-')
        
        print(f"● Update({filepath})")
        print(f"  └─ Updated {filepath} with {additions} addition{'s' if additions != 1 else ''}")
        
        # Diff with line numbers
        for line in diff:
            lineno = f"{line.number:>4}"
            if line.type == '+':
                # Green for additions
                print(f"  {lineno} + {green(line.content)}")
            elif line.type == '-':
                # Red for deletions
                print(f"  {lineno} - {red(line.content)}")
            else:
                # Gray for context
                print(f"     {lineno}  {dim(line.content)}")
```

---

**Key UX details:**

| Element | Write Card | Update Card |
|---------|------------|-------------|
| Header | `● Write(path)` | `● Update(path)` |
| Summary | Line count | Addition/deletion count |
| Content | Raw preview (highlighted) | Diff view with +/- |
| Line numbers | No | Yes (right-aligned) |
| Colors | Syntax highlighting | Green (+), Red (-), Dim (context) |
| Collapse | `… +N lines` | Only if diff is long |
| Expand | `ctrl+o` | `ctrl+o` |