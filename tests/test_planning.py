"""
Planning Middleware Tests

Tests for TodoList, TodoItem, and PlanningMiddleware.
"""

import pytest

from vel_harness.middleware.planning import (
    PlanningMiddleware,
    TodoItem,
    TodoList,
)


class TestTodoItem:
    """Tests for TodoItem."""

    def test_create_item(self) -> None:
        """Test creating a todo item."""
        item = TodoItem(id="todo_0", task="Test task")

        assert item.id == "todo_0"
        assert item.task == "Test task"
        assert item.status == "pending"
        assert item.created_at is not None
        assert item.completed_at is None
        assert item.notes is None

    def test_to_dict(self) -> None:
        """Test converting to dictionary."""
        item = TodoItem(id="todo_0", task="Test task", notes="Some notes")
        data = item.to_dict()

        assert data["id"] == "todo_0"
        assert data["task"] == "Test task"
        assert data["status"] == "pending"
        assert data["notes"] == "Some notes"

    def test_from_dict(self) -> None:
        """Test creating from dictionary."""
        data = {
            "id": "todo_1",
            "task": "Another task",
            "status": "done",
            "created_at": "2024-01-01T00:00:00Z",
            "completed_at": "2024-01-02T00:00:00Z",
            "notes": "Completed successfully",
        }
        item = TodoItem.from_dict(data)

        assert item.id == "todo_1"
        assert item.task == "Another task"
        assert item.status == "done"
        assert item.completed_at == "2024-01-02T00:00:00Z"


class TestTodoList:
    """Tests for TodoList."""

    def test_add_item(self, todo_list: TodoList) -> None:
        """Test adding items."""
        item = todo_list.add("First task")

        assert item.id == "todo_0"
        assert item.task == "First task"
        assert len(todo_list.items) == 1

        # Add another
        item2 = todo_list.add("Second task")
        assert item2.id == "todo_1"
        assert len(todo_list.items) == 2

    def test_complete_item(self, todo_list: TodoList) -> None:
        """Test completing an item."""
        todo_list.add("Task to complete")

        result = todo_list.complete("todo_0")
        assert result is True

        item = todo_list.get_by_id("todo_0")
        assert item is not None
        assert item.status == "done"
        assert item.completed_at is not None

    def test_complete_with_notes(self, todo_list: TodoList) -> None:
        """Test completing with notes."""
        todo_list.add("Task")
        todo_list.complete("todo_0", notes="Done with changes")

        item = todo_list.get_by_id("todo_0")
        assert item is not None
        assert item.notes == "Done with changes"

    def test_complete_nonexistent(self, todo_list: TodoList) -> None:
        """Test completing non-existent item."""
        result = todo_list.complete("nonexistent")
        assert result is False

    def test_start_item(self, todo_list: TodoList) -> None:
        """Test starting an item."""
        todo_list.add("Task to start")

        result = todo_list.start("todo_0")
        assert result is True

        item = todo_list.get_by_id("todo_0")
        assert item is not None
        assert item.status == "in_progress"

    def test_block_item(self, todo_list: TodoList) -> None:
        """Test blocking an item."""
        todo_list.add("Task to block")

        result = todo_list.block("todo_0", "Waiting for external input")
        assert result is True

        item = todo_list.get_by_id("todo_0")
        assert item is not None
        assert item.status == "blocked"
        assert item.notes == "Waiting for external input"

    def test_get_pending(self, populated_todo_list: TodoList) -> None:
        """Test getting pending items."""
        pending = populated_todo_list.get_pending()

        assert len(pending) == 2  # Two items should still be pending
        for item in pending:
            assert item.status == "pending"

    def test_get_in_progress(self, populated_todo_list: TodoList) -> None:
        """Test getting in-progress items."""
        in_progress = populated_todo_list.get_in_progress()

        assert len(in_progress) == 1
        assert in_progress[0].id == "todo_1"

    def test_get_completed(self, populated_todo_list: TodoList) -> None:
        """Test getting completed items."""
        completed = populated_todo_list.get_completed()

        assert len(completed) == 1
        assert completed[0].id == "todo_0"

    def test_get_by_id(self, populated_todo_list: TodoList) -> None:
        """Test getting item by ID."""
        item = populated_todo_list.get_by_id("todo_0")
        assert item is not None
        assert item.task == "Load data"

        # Non-existent
        item2 = populated_todo_list.get_by_id("nonexistent")
        assert item2 is None

    def test_to_markdown(self, populated_todo_list: TodoList) -> None:
        """Test markdown rendering."""
        markdown = populated_todo_list.to_markdown()

        # Should include current task
        assert "Working on analysis" in markdown

        # Should have items with checkboxes
        assert "[x]" in markdown  # Completed item
        assert "[ ]" in markdown  # Pending items

        # Should include task names
        assert "Load data" in markdown
        assert "Process data" in markdown

        # Should have summary
        assert "Summary" in markdown
        assert "Pending:" in markdown
        assert "Completed:" in markdown

    def test_clear(self, populated_todo_list: TodoList) -> None:
        """Test clearing the list."""
        populated_todo_list.clear()

        assert len(populated_todo_list.items) == 0
        assert populated_todo_list.current_task == ""


class TestPlanningMiddleware:
    """Tests for PlanningMiddleware."""

    def test_get_tools(self, planning_middleware: PlanningMiddleware) -> None:
        """Test that middleware returns tools."""
        tools = planning_middleware.get_tools()

        tool_names = [t.name for t in tools]
        assert "write_todos" in tool_names
        assert "read_todos" in tool_names

    def test_tool_has_correct_category(self, planning_middleware: PlanningMiddleware) -> None:
        """Test that tool has planning category."""
        tools = planning_middleware.get_tools()
        for tool in tools:
            assert tool.category == "planning"

    def test_system_prompt_segment(self, planning_middleware: PlanningMiddleware) -> None:
        """Test system prompt segment."""
        segment = planning_middleware.get_system_prompt_segment()

        assert "Planning" in segment
        assert "write_todos" in segment
        assert "next_steps" in segment

    def test_write_todos_add_items(self, planning_middleware: PlanningMiddleware) -> None:
        """Test adding new todo items."""
        result = planning_middleware.write_todos(
            current_task="Starting analysis",
            next_steps=["Load data", "Process data", "Generate report"],
        )

        assert result["current_task"] == "Starting analysis"
        assert len(result["new_items"]) == 3
        assert result["pending_count"] == 3

    def test_write_todos_complete_items(self, planning_middleware: PlanningMiddleware) -> None:
        """Test completing items."""
        # First add items
        planning_middleware.write_todos(
            current_task="Setup",
            next_steps=["Step 1", "Step 2"],
        )

        # Complete first item
        result = planning_middleware.write_todos(
            current_task="Working on step 2",
            completed=["todo_0"],
        )

        assert result["completed_count"] == 1
        assert result["pending_count"] == 1
        assert len(result["completed_items"]) == 1

    def test_write_todos_start_items(self, planning_middleware: PlanningMiddleware) -> None:
        """Test marking items as in progress."""
        planning_middleware.write_todos(
            current_task="Setup",
            next_steps=["Step 1"],
        )

        result = planning_middleware.write_todos(
            current_task="Working",
            in_progress=["todo_0"],
        )

        assert result["in_progress_count"] == 1
        assert len(result["started_items"]) == 1

    def test_write_todos_block_items(self, planning_middleware: PlanningMiddleware) -> None:
        """Test blocking items."""
        planning_middleware.write_todos(
            current_task="Setup",
            next_steps=["Blocked task"],
        )

        result = planning_middleware.write_todos(
            current_task="Waiting",
            blocked=[{"id": "todo_0", "reason": "Need more info"}],
        )

        assert result["blocked_count"] == 1
        assert len(result["blocked_items"]) == 1
        assert result["blocked_items"][0]["notes"] == "Need more info"

    def test_write_todos_combined_operations(
        self, planning_middleware: PlanningMiddleware
    ) -> None:
        """Test multiple operations in one call."""
        # Setup initial items
        planning_middleware.write_todos(
            current_task="Initial",
            next_steps=["Task A", "Task B", "Task C"],
        )

        # Combined update
        result = planning_middleware.write_todos(
            current_task="Working on Task B",
            next_steps=["Task D"],  # Add new
            completed=["todo_0"],  # Complete A
            in_progress=["todo_1"],  # Start B
        )

        assert result["current_task"] == "Working on Task B"
        assert result["completed_count"] == 1
        assert result["in_progress_count"] == 1
        assert result["pending_count"] == 2  # C and D
        assert len(result["new_items"]) == 1

    def test_write_todos_returns_markdown(
        self, planning_middleware: PlanningMiddleware
    ) -> None:
        """Test that result includes markdown view."""
        result = planning_middleware.write_todos(
            current_task="Test",
            next_steps=["Step 1"],
        )

        assert "todo_list" in result
        assert "Step 1" in result["todo_list"]

    def test_read_todos(self, planning_middleware: PlanningMiddleware) -> None:
        """Test reading todo state."""
        planning_middleware.write_todos(
            current_task="Testing",
            next_steps=["Step 1", "Step 2"],
        )
        result = planning_middleware.read_todos()
        assert result["current_task"] == "Testing"
        assert result["pending_count"] == 2
        assert "Step 1" in result["todo_list"]

    def test_state_persistence(self, planning_middleware: PlanningMiddleware) -> None:
        """Test state serialization and restoration."""
        # Add some items
        planning_middleware.write_todos(
            current_task="Persisted task",
            next_steps=["Step 1", "Step 2"],
        )
        planning_middleware.write_todos(
            current_task="Working",
            completed=["todo_0"],
        )

        # Get state
        state = planning_middleware.get_state()

        # Create new middleware and load state
        new_middleware = PlanningMiddleware()
        new_middleware.load_state(state)

        # Verify state is restored
        assert new_middleware.todo_list.current_task == "Working"
        assert len(new_middleware.todo_list.items) == 2
        assert new_middleware.todo_list.get_by_id("todo_0").status == "done"
        assert new_middleware.todo_list.get_by_id("todo_1").status == "pending"
