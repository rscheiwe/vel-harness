# VelHarness Examples

This directory contains examples demonstrating VelHarness features.
All examples run directly without needing an API server.

## Prerequisites

```bash
# Install dependencies (from project root)
pip install -e .
pip install python-dotenv

# API key is loaded from .env file in project root
# Create .env with:
# ANTHROPIC_API_KEY=your_key_here
```

## Examples

### 1. Quickstart (`quickstart.py`)

Basic usage showing simple responses, tool use, and skill loading.

```bash
python examples/quickstart.py
```

### 2. Feature Tests (`test_all_features.py`)

Comprehensive test suite covering all harness capabilities:
- Bash execution
- File read/write
- Glob/Grep search
- Skill loading (tool_result injection)
- Todo planning
- Session continuity
- Subagent spawning (explore, plan)
- Agent registry

```bash
# Run all tests
python examples/test_all_features.py

# Run specific test
python examples/test_all_features.py --test skill
python examples/test_all_features.py --test bash
python examples/test_all_features.py --test explore

# With streaming output
python examples/test_all_features.py --stream
```

### 3. Streaming (`streaming_example.py`)

Demonstrates Vercel AI SDK V5 streaming protocol:
- Text deltas
- Tool calls and results
- Stream events handling

```bash
python examples/streaming_example.py
```

### 4. Subagents (`subagent_example.py`)

Shows typed subagent usage:
- Explore agent (read-only)
- Plan agent (structured planning)
- Custom agent registration
- Parallel subagent pattern

```bash
python examples/subagent_example.py
```

## Sample Skills

The `skills/` directory contains sample skills for testing:

- **code_review.md** - Code review guidelines
- **research.md** - Research methodology
- **test_skill.md** - Simple verification skill

### Skill Format

Skills use YAML frontmatter + Markdown:

```markdown
---
name: My Skill
description: What this skill does
tags:
  - tag1
  - tag2
triggers:
  - trigger phrase
  - pattern*
priority: 10
---

# Skill Content

Instructions in Markdown...
```

## Testing Checklist

| Feature | Test Command | Expected |
|---------|--------------|----------|
| Basic response | `--test simple` | Answers correctly |
| Bash tool | `--test bash` | Executes command |
| File read | `--test read` | Reads content |
| File write | `--test write` | Creates file |
| Glob | `--test glob` | Finds files |
| Grep | `--test grep` | Finds content |
| Skill load | `--test skill` | Returns skill content |
| Todo | `--test todo` | Creates todos |
| Session | `--test session` | Maintains context |
| Explore agent | `--test explore` | Read-only investigation |
| Plan agent | `--test plan` | Structured plan |
