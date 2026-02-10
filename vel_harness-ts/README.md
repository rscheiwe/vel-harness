# vel-harness-ts

TypeScript Agent Harness - Claude Code-style capabilities built on vel-ts runtime.

## Features

- **Skills System**: Load and activate procedural knowledge from SKILL.md files
- **Subagent Spawning**: Delegate tasks to specialized agents (explore, plan, default)
- **Planning Tools**: TodoWrite for explicit task tracking
- **File Operations**: Read, write, edit, glob, grep
- **Streaming**: Full Vercel AI SDK v5 protocol support

## Installation

```bash
npm install vel-harness-ts vel-ts
```

## Quick Start

```typescript
import { createHarness } from 'vel-harness-ts';

const harness = createHarness({
  model: { provider: 'anthropic', model: 'claude-sonnet-4-5-20250929' },
  skillDirs: ['./skills'],
});

// Non-streaming
const response = await harness.run('Analyze the codebase');

// Streaming
for await (const event of harness.runStream('Write a function')) {
  if (event.type === 'text-delta') {
    process.stdout.write(event.delta);
  }
}
```

## Skills

Skills are Markdown files with YAML frontmatter:

```markdown
---
name: "SQL Analysis"
description: "Guidelines for SQL query analysis"
triggers:
  - "sql"
  - "database*"
tags:
  - "database"
priority: 10
---

## SQL Analysis Guidelines

When analyzing SQL queries...
```

Skills are injected as `tool_result` to preserve Anthropic prompt caching.

## Subagents

Spawn specialized agents for task delegation:

```typescript
// The agent can use:
// - spawn_subagent(task, agent="explore") - Read-only exploration
// - spawn_subagent(task, agent="plan") - Structured planning
// - spawn_subagent(task, agent="default") - Full capabilities
// - spawn_parallel(tasks) - Parallel execution
```

## Factory Functions

```typescript
import {
  createHarness,        // Default configuration
  createResearchHarness, // Research-focused
  createCodingHarness,   // Coding-focused
  createMinimalHarness,  // No skills, no planning
} from 'vel-harness-ts';
```

## API

### VelHarness

```typescript
class VelHarness {
  // Run agent
  run(message: string, options?: RunOptions): Promise<string>;
  runStream(message: string, options?: RunOptions): AsyncGenerator<StreamEvent>;

  // Agent management
  registerAgent(agentId: string, config: SubagentConfig): void;
  listAgentTypes(): string[];

  // State
  getState(): Record<string, unknown>;
  loadState(state: Record<string, Record<string, unknown>>): void;
}
```

### RunOptions

```typescript
interface RunOptions {
  sessionId?: string;
  context?: Record<string, unknown>;
  generationConfig?: GenerationConfig;
  metadata?: Record<string, unknown>;
}
```

## License

MIT
