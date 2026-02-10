That's the **TodoWrite integration** with the status line. When Claude Code has an active todo list, the status shows:

```
* Current todo item... (esc to interrupt)
└─ Next: Next todo item
```

Instead of generic verbs when there's no plan.

---

**Two modes:**

| State | Status Display |
|-------|----------------|
| No todos | `∴ Gesticulating...` / `Harmonizing...` (random verbs) |
| Active todos | `* Implementing feature X...` + `└─ Next: Y` |

---

**Implementation concept:**

```python
class StatusLine:
    def render(self) -> str:
        todos = self.agent.get_current_todos()
        
        if todos and todos.current:
            # Show task-aware status
            current = todos.current
            next_item = todos.next
            
            status = f"* {current.title}… (esc to interrupt)"
            if next_item:
                status += f"\n└─ Next: {next_item.title}"
            return status
        else:
            # Generic thinking verb
            verb = random.choice(THINKING_VERBS)
            return f"∴ {verb}… (ctrl+o to show thinking)"
```

---

**The todo structure Claude Code uses:**

```python
@dataclass
class TodoItem:
    id: str
    title: str
    status: Literal["pending", "in_progress", "done"]

# When agent calls write_todos, status line reads from it
todos = [
    TodoItem("1", "Implementing watchdog file watcher", "in_progress"),
    TodoItem("2", "Test drag-drop with watchdog", "pending"),
    TodoItem("3", "Wire up to input widget", "pending"),
]
```

---

For Valis, you'd hook the `TodoMiddleware` into the status bar widget to show current task context instead of generic verbs.