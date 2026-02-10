"""
Todo/task tracking tool prompt.
Source: Piebald claude-code-system-prompts (adapted)
"""

TODO_WRITE_PROMPT = """
# Task Tracking Tool Guidelines

Use `write_todos` and `read_todos` to manage a structured task list for the current session.

## Purpose

- Track progress on complex tasks
- Organize multi-step work
- Give the user visibility into your progress
- Plan tasks and break down larger work into smaller steps

## When to Use This Tool

Use proactively in these scenarios:

1. **Complex multi-step tasks** - When a task requires 3 or more distinct steps
2. **Non-trivial tasks** - Tasks requiring careful planning or multiple operations
3. **User explicitly requests** - When directly asked to use the todo list
4. **Multiple tasks provided** - When users provide a list (numbered or comma-separated)
5. **After receiving new instructions** - Immediately capture requirements as todos
6. **Starting work on a task** - Mark as in_progress BEFORE beginning
7. **After completing a task** - Mark as completed and add any discovered follow-up tasks

## When NOT to Use

Skip using this tool when:
1. Single, straightforward task
2. Trivial task with no organizational benefit
3. Task can be completed in less than 3 trivial steps
4. Purely conversational or informational request

## Task States

- **pending**: Task not yet started
- **in_progress**: Currently working on (limit to ONE at a time)
- **completed**: Task finished successfully

## Task Management Rules

1. Update status in real-time as you work
2. Mark tasks complete IMMEDIATELY after finishing (don't batch)
3. Exactly ONE task should be in_progress at any time
4. Complete current tasks before starting new ones
5. Remove tasks that are no longer relevant

## Task Completion Requirements

ONLY mark a task as completed when you have FULLY accomplished it. Never mark completed if:
- Tests are failing
- Implementation is partial
- You encountered unresolved errors
- You couldn't find necessary files or dependencies

When blocked, create a new task describing what needs resolution.

## Task Descriptions

Always provide both forms:
- **content**: Imperative form ("Run tests", "Build the project")
- **activeForm**: Present continuous ("Running tests", "Building the project")

## Examples

### Good Use Cases

**User**: "Add dark mode toggle, run tests and build when done"
- Create todos for: toggle component, state management, styling, tests, build
- Work through each systematically

**User**: "Rename getCwd to getCurrentWorkingDirectory across the project"
- First search to find all occurrences
- Create todos for each file needing updates

### Skip the Todo List

**User**: "How do I print 'Hello World' in Python?"
- Single trivial task - just answer directly

**User**: "Add a comment to the calculateTotal function"
- Single edit in one location - just do it
"""

# Token count estimate
TOKEN_ESTIMATE = 550
