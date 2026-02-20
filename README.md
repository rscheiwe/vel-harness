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
- **RunGuard**: Deterministic runtime guardrails for budgets/loop prevention/completion gating

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

# Run lightweight smoke checks (no external API calls)
make smoke

# Syntax compile check
make compile

# Run tests
pytest

# Format code
black vel_harness tests
ruff check vel_harness tests
```

Recommended local test environment (to avoid Conda/Python capture issues):

```bash
/opt/homebrew/bin/python3.11 -m venv .venv311
.venv311/bin/python -m pip install pytest pytest-asyncio pytest-mock anyio pytest-cov
.venv311/bin/python -m pip install httpx pydantic jsonschema python-dotenv tenacity jinja2 openai google-generativeai anthropic pyyaml textual click rich
PYTHONPATH=/Users/richard.s/vel .venv311/bin/python -m pytest -q
```

## Operations Docs

For consolidated runbooks (testing, trace analysis, and experiment comparison), see:

- `docs/HARNESS_OPERATIONS.md`

### Trace Analysis Quick Commands

```bash
# Analyze raw trace export
make analyze-traces INPUT=traces.json OUTPUT=analysis.json

# Compare baseline vs candidate experiment outputs
make compare-experiments BASELINE=baseline_analysis.json CANDIDATE=candidate_analysis.json OUTPUT=comparison.json

# Full experiment cycle report (baseline + candidate + comparison)
make experiment-cycle BASELINE=baseline_traces.json CANDIDATE=candidate_traces.json OUT_JSON=cycle.json OUT_MD=cycle.md

# Reproducible experiment bundle (config + prompt + optional analysis/comparison)
python scripts/run_harness_experiment.py --name exp-1 --output-dir .experiments --trace-input traces.json
```

### One-Call Role Workflow

```python
result = await harness.run_role_workflow(
    goal="discover -> implement -> verify -> critic pipeline",
    include_critic=True,
)
```

## License

MIT
