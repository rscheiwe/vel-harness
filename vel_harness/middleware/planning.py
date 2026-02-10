"""
Planning Middleware

Provides a todo list tool for planning and tracking complex tasks.
Mirrors Claude Code's planning behavior.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from vel import ToolSpec

from vel_harness.middleware.base import BaseMiddleware


@dataclass
class TodoItem:
    """A single todo item."""

    id: str
    task: str
    status: str = "pending"  # pending, in_progress, done, blocked
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "task": self.task,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TodoItem":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            task=data["task"],
            status=data.get("status", "pending"),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            completed_at=data.get("completed_at"),
            notes=data.get("notes"),
        )


@dataclass
class TodoList:
    """Manages the todo list state."""

    items: List[TodoItem] = field(default_factory=list)
    current_task: str = ""
    _next_id: int = 0

    def add(self, task: str) -> TodoItem:
        """Add a new todo item."""
        item = TodoItem(
            id=f"todo_{self._next_id}",
            task=task,
        )
        self._next_id += 1
        self.items.append(item)
        return item

    def complete(self, todo_id: str, notes: Optional[str] = None) -> bool:
        """Mark a todo item as complete."""
        for item in self.items:
            if item.id == todo_id:
                item.status = "done"
                item.completed_at = datetime.now(timezone.utc).isoformat()
                if notes:
                    item.notes = notes
                return True
        return False

    def start(self, todo_id: str) -> bool:
        """Mark a todo item as in progress."""
        for item in self.items:
            if item.id == todo_id:
                item.status = "in_progress"
                return True
        return False

    def block(self, todo_id: str, reason: str) -> bool:
        """Mark a todo item as blocked."""
        for item in self.items:
            if item.id == todo_id:
                item.status = "blocked"
                item.notes = reason
                return True
        return False

    def get_by_id(self, todo_id: str) -> Optional[TodoItem]:
        """Get a todo item by ID."""
        for item in self.items:
            if item.id == todo_id:
                return item
        return None

    def get_pending(self) -> List[TodoItem]:
        """Get all pending items."""
        return [t for t in self.items if t.status == "pending"]

    def get_in_progress(self) -> List[TodoItem]:
        """Get all in-progress items."""
        return [t for t in self.items if t.status == "in_progress"]

    def get_completed(self) -> List[TodoItem]:
        """Get all completed items."""
        return [t for t in self.items if t.status == "done"]

    def get_blocked(self) -> List[TodoItem]:
        """Get all blocked items."""
        return [t for t in self.items if t.status == "blocked"]

    def to_markdown(self) -> str:
        """Render todo list as markdown."""
        lines = ["## Current Task", f"{self.current_task or '(none)'}", "", "## Todo List"]

        if not self.items:
            lines.append("(empty)")
            return "\n".join(lines)

        status_emoji = {
            "pending": "",
            "in_progress": "",
            "done": "",
            "blocked": "",
        }

        for item in self.items:
            checkbox = "x" if item.status == "done" else " "
            emoji = status_emoji.get(item.status, "")

            lines.append(f"- [{checkbox}] {emoji} {item.task} (`{item.id}`)")
            if item.notes:
                lines.append(f"  - Note: {item.notes}")

        # Summary
        pending = len(self.get_pending())
        in_progress = len(self.get_in_progress())
        done = len(self.get_completed())
        blocked = len(self.get_blocked())

        lines.extend(
            [
                "",
                "## Summary",
                f"- Pending: {pending}",
                f"- In Progress: {in_progress}",
                f"- Completed: {done}",
                f"- Blocked: {blocked}",
            ]
        )

        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all items."""
        self.items.clear()
        self.current_task = ""
        self._next_id = 0


class PlanningMiddleware(BaseMiddleware):
    """
    Middleware that provides planning capabilities via a todo list.

    Adds the `write_todos` tool to the agent.
    """

    def __init__(self) -> None:
        """Initialize planning middleware."""
        self.todo_list = TodoList()

    def get_tools(self) -> List[ToolSpec]:
        """Return planning tools."""
        return [
            ToolSpec.from_function(
                self.write_todos,
                name="write_todos",
                description="""
Update the todo list with current progress and next steps.
Use this tool to:
- Plan out complex tasks before starting
- Track progress on multi-step work
- Mark items complete as you finish them
- Adapt your plan when new information emerges

Always create a plan before starting complex work.
                """.strip(),
                category="planning",
                tags=["planning", "tracking"],
            ),
        ]

    def write_todos(
        self,
        current_task: str,
        next_steps: Optional[List[str]] = None,
        completed: Optional[List[str]] = None,
        in_progress: Optional[List[str]] = None,
        blocked: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Update the todo list with current progress and next steps.

        Args:
            current_task: What you're working on right now (brief description)
            next_steps: List of upcoming tasks to add to the todo list
            completed: List of todo IDs that are now done (e.g., ['todo_0', 'todo_1'])
            in_progress: List of todo IDs that are now in progress
            blocked: List of blocked items: [{"id": "todo_2", "reason": "Waiting for data"}]

        Returns:
            Current state of the todo list including markdown view
        """
        # Update current task
        self.todo_list.current_task = current_task

        # Mark completed
        completed_items: List[Dict[str, Any]] = []
        if completed:
            for todo_id in completed:
                if self.todo_list.complete(todo_id):
                    item = self.todo_list.get_by_id(todo_id)
                    if item:
                        completed_items.append(item.to_dict())

        # Mark in progress
        started_items: List[Dict[str, Any]] = []
        if in_progress:
            for todo_id in in_progress:
                if self.todo_list.start(todo_id):
                    item = self.todo_list.get_by_id(todo_id)
                    if item:
                        started_items.append(item.to_dict())

        # Mark blocked
        blocked_items: List[Dict[str, Any]] = []
        if blocked:
            for block_info in blocked:
                todo_id = block_info.get("id", "")
                reason = block_info.get("reason", "")
                if self.todo_list.block(todo_id, reason):
                    item = self.todo_list.get_by_id(todo_id)
                    if item:
                        blocked_items.append(item.to_dict())

        # Add new steps
        new_items: List[Dict[str, Any]] = []
        if next_steps:
            for step in next_steps:
                item = self.todo_list.add(step)
                new_items.append(item.to_dict())

        return {
            "current_task": current_task,
            "new_items": new_items,
            "completed_items": completed_items,
            "started_items": started_items,
            "blocked_items": blocked_items,
            "pending_count": len(self.todo_list.get_pending()),
            "in_progress_count": len(self.todo_list.get_in_progress()),
            "completed_count": len(self.todo_list.get_completed()),
            "blocked_count": len(self.todo_list.get_blocked()),
            "todo_list": self.todo_list.to_markdown(),
        }

    def get_system_prompt_segment(self) -> str:
        """Return system prompt segment for planning."""
        return """
## Planning

You have a `write_todos` tool for planning and tracking complex tasks.

**When to use planning:**
- Before starting any task that requires multiple steps
- When you need to break down a complex request
- To track progress on ongoing work
- When you need to adapt your approach based on new information

**How to plan effectively:**
1. Start by identifying the high-level goal
2. Break it down into concrete, actionable steps
3. Update the plan as you learn more
4. Mark items complete as you finish them
5. Mark items as blocked if you hit obstacles

**Example:**
User asks: "Analyze our Q4 sales data and create a report"

You should first call write_todos:
```
write_todos(
    current_task="Analyzing Q4 sales data",
    next_steps=[
        "Load and examine the sales data structure",
        "Calculate key metrics (total revenue, growth, top products)",
        "Create visualizations for trends",
        "Write executive summary",
        "Compile final report"
    ]
)
```

Then work through each step, updating the plan:
```
write_todos(
    current_task="Calculating key metrics",
    completed=["todo_0"],
    in_progress=["todo_1"]
)
```
"""

    def get_state(self) -> Dict[str, Any]:
        """Get current planning state for persistence."""
        return {
            "current_task": self.todo_list.current_task,
            "items": [item.to_dict() for item in self.todo_list.items],
            "_next_id": self.todo_list._next_id,
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load planning state from persistence."""
        self.todo_list.current_task = state.get("current_task", "")
        self.todo_list._next_id = state.get("_next_id", 0)
        self.todo_list.items = [TodoItem.from_dict(item) for item in state.get("items", [])]
