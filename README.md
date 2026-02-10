# Vel Harness

Deep agent framework built on [Vel](https://github.com/example/vel) (agent runtime) and [Mesh](https://github.com/example/mesh) (graph orchestration).

## Features

- **Planning**: Todo list tool for breaking down and tracking complex tasks
- **Filesystem**: Read, write, edit, glob, and grep files
- **Sandbox**: Secure code execution (macOS Seatbelt, Linux bubblewrap)
- **Skills**: Procedural knowledge documents (SKILL.md) for domain expertise
- **Database**: SQL execution with safety controls
- **Subagents**: Spawn parallel subagents for deep research
- **Human-in-the-Loop**: Interrupt execution for approval workflows

## Installation

```bash
pip install vel-harness
```

For database support:
```bash
pip install vel-harness[database]
```

## Quick Start

```python
from vel_harness import create_deep_agent

agent = create_deep_agent(
    model={"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
    skill_dirs=["./skills"],
    sandbox=True,
)

result = await agent.run("Analyze the sales data and create a report")
```

## CLI Usage

```bash
# Interactive mode
vel-harness

# Run a task
vel-harness "Analyze Q4 sales data"

# With options
vel-harness --model gpt-4 --workspace ./work "Create a report"
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black vel_harness tests
ruff check vel_harness tests
```

## License

MIT

