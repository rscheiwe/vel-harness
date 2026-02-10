"""
Pytest Configuration and Shared Fixtures

Provides fixtures for testing vel_harness components.
"""

import pytest
from typing import Generator

from vel_harness.backends.state import StateFilesystemBackend
from vel_harness.middleware.filesystem import FilesystemMiddleware
from vel_harness.middleware.planning import PlanningMiddleware, TodoList


@pytest.fixture
def state_backend() -> StateFilesystemBackend:
    """Create a fresh in-memory filesystem backend."""
    return StateFilesystemBackend()


@pytest.fixture
def populated_backend() -> StateFilesystemBackend:
    """Create a backend with sample files."""
    backend = StateFilesystemBackend()

    # Create sample files
    backend.write_file("/readme.md", "# My Project\n\nThis is a test project.")
    backend.write_file("/data/sales.csv", "date,amount,product\n2024-01-01,100,Widget\n2024-01-02,150,Gadget")
    backend.write_file("/data/users.csv", "id,name,email\n1,Alice,alice@example.com\n2,Bob,bob@example.com")
    backend.write_file("/reports/q1.md", "# Q1 Report\n\nSales increased by 10%.")
    backend.write_file("/src/main.py", "def main():\n    print('Hello, world!')\n\nif __name__ == '__main__':\n    main()")
    backend.write_file("/src/utils.py", "def helper():\n    return 42\n")

    return backend


@pytest.fixture
def filesystem_middleware(state_backend: StateFilesystemBackend) -> FilesystemMiddleware:
    """Create filesystem middleware with fresh backend."""
    return FilesystemMiddleware(backend=state_backend)


@pytest.fixture
def populated_filesystem_middleware(populated_backend: StateFilesystemBackend) -> FilesystemMiddleware:
    """Create filesystem middleware with sample files."""
    return FilesystemMiddleware(backend=populated_backend)


@pytest.fixture
def planning_middleware() -> PlanningMiddleware:
    """Create fresh planning middleware."""
    return PlanningMiddleware()


@pytest.fixture
def todo_list() -> TodoList:
    """Create fresh todo list."""
    return TodoList()


@pytest.fixture
def populated_todo_list() -> TodoList:
    """Create todo list with sample items."""
    todo_list = TodoList()
    todo_list.current_task = "Working on analysis"

    todo_list.add("Load data")
    todo_list.add("Process data")
    todo_list.add("Generate report")
    todo_list.add("Review results")

    # Mark first item as done
    todo_list.complete("todo_0")
    # Mark second as in progress
    todo_list.start("todo_1")

    return todo_list


@pytest.fixture
def sample_skill_content() -> str:
    """Sample SKILL.md content for testing."""
    return """---
name: data-query
description: Query databases and analyze data
version: 1.0.0
author: Test Author
tools_required:
  - execute_sql
  - execute_python
tags:
  - data
  - sql
  - analysis
---

# Data Query Skill

## When to Use

Use this skill when analyzing data or querying databases.

## Approach

1. Understand the data structure
2. Write queries incrementally
3. Validate results

## Examples

```sql
SELECT * FROM users LIMIT 10;
```
"""
