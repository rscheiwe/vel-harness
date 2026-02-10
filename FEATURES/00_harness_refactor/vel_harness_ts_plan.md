# vel_harness-ts: TypeScript Agent Harness Assessment & Implementation Plan

## Executive Summary

This document outlines the conversion of `vel_harness` (Python) to `vel_harness-ts` (TypeScript), creating a parallel TypeScript implementation that runs on top of the `vel-ts` agent framework. The TypeScript version will provide identical Claude Code-style capabilities (skills, subagents, planning, context management) while leveraging vel-ts's existing infrastructure.

**Key Findings:**
- vel-ts already provides ~70% of needed infrastructure (providers, tools, streaming, hooks)
- Primary work is building the middleware layer and Claude Code patterns
- Skills system, subagent spawning, and context management are the main new components
- TypeScript patterns will differ from Python (composition over inheritance)

---

## Table of Contents

1. [Python vel_harness Architecture Analysis](#1-python-vel_harness-architecture-analysis)
2. [vel-ts Capabilities Assessment](#2-vel-ts-capabilities-assessment)
3. [Component Mapping: Python → TypeScript](#3-component-mapping-python--typescript)
4. [Gap Analysis](#4-gap-analysis)
5. [TypeScript Implementation Strategy](#5-typescript-implementation-strategy)
6. [Detailed Implementation Plan](#6-detailed-implementation-plan)
7. [Directory Structure](#7-directory-structure)
8. [API Design](#8-api-design)
9. [Migration Path & Compatibility](#9-migration-path--compatibility)
10. [Testing Strategy](#10-testing-strategy)
11. [Work Breakdown & Phases](#11-work-breakdown--phases)

---

## 1. Python vel_harness Architecture Analysis

### 1.1 Core Components

| Component | Purpose | Lines of Code | Complexity |
|-----------|---------|---------------|------------|
| **VelHarness** | Primary public API | ~150 | Medium |
| **DeepAgent** | Internal agent wrapper | ~300 | High |
| **Middleware System** | Pluggable capabilities | ~2500 | High |
| **Backends** | Storage & execution | ~1500 | High |
| **Skills** | Procedural knowledge | ~400 | Medium |
| **Subagents** | Task delegation | ~500 | Medium |
| **Prompts** | Modular system prompts | ~800 | Low |
| **Config** | Configuration dataclasses | ~200 | Low |

### 1.2 Middleware Architecture (Python)

```
BaseMiddleware (abstract)
├── get_tools() → List[ToolSpec]
├── get_system_prompt_segment() → str
├── get_state() → Dict
└── load_state(state: Dict) → None

Implementations:
├── PlanningMiddleware       # TodoWrite/TodoRead
├── FilesystemMiddleware     # Read/Write/Edit/Glob/Grep
├── SandboxMiddleware        # Execute/ExecutePython
├── DatabaseMiddleware       # SQL queries
├── SkillsMiddleware         # Skill activation
├── SubagentsMiddleware      # Spawn/Wait/Cancel
├── ContextManagementMiddleware  # Truncation/Offload
├── MemoryMiddleware         # Persistent knowledge
├── CachingMiddleware        # Prompt caching
└── RetryMiddleware          # Error recovery
```

### 1.3 Key Design Patterns

1. **Middleware Pattern**: Each capability is a plugin with tools + prompts
2. **Backend Protocol**: Structural typing for filesystem/database operations
3. **Factory Pattern**: Configuration-driven agent assembly
4. **Tool Result Injection**: Skills as tool output (not system prompt)
5. **State Management**: Serializable state for persistence

### 1.4 Skill System Details

```python
@dataclass
class Skill:
    name: str
    description: str
    content: str              # Markdown content
    triggers: List[str]       # Auto-activation patterns
    tags: List[str]           # Categorization
    priority: int             # Ordering
    requires: List[str]       # Dependencies
```

**Injection Modes:**
- `TOOL_RESULT`: Skills returned as tool_result (preserves prompt caching)
- `SYSTEM_PROMPT`: Added to system prompt (legacy, breaks caching)

### 1.5 Subagent System Details

```python
DEFAULT_AGENTS = {
    "default": AgentConfig(
        tools=["execute", "read_file", "write_file", "edit_file",
               "ls", "glob", "grep", "write_todos"],
        max_turns=50,
        description="General-purpose task execution",
    ),
    "explore": AgentConfig(
        tools=["read_file", "ls", "glob", "grep", "execute"],
        max_turns=30,
        description="Read-only codebase exploration",
    ),
    "plan": AgentConfig(
        tools=["read_file", "ls", "glob", "grep", "write_todos"],
        max_turns=20,
        description="Structured planning and task breakdown",
    ),
}
```

---

## 2. vel-ts Capabilities Assessment

### 2.1 What vel-ts Already Provides

| Capability | Status | Notes |
|------------|--------|-------|
| **Multi-Provider** | ✅ Complete | OpenAI, Anthropic, Google |
| **Tool System** | ✅ Complete | ToolSpec, Zod schemas, streaming tools |
| **Streaming** | ✅ Complete | Vercel AI SDK v5 protocol |
| **Hooks** | ✅ Complete | Full lifecycle callbacks |
| **Guardrails** | ✅ Complete | Input/output/tool validation |
| **Session Management** | ✅ Complete | Stateful/stateless modes |
| **Message History** | ✅ Complete | ContextManager |
| **Structured Output** | ✅ Complete | JSON streaming with Zod |
| **Prompt Templates** | ✅ Complete | Nunjucks-based |
| **Memory Systems** | ⚠️ Partial | SQLite-backed, needs adaptation |
| **Tool Registry** | ✅ Complete | Global + instance + injected |
| **Error Handling** | ✅ Complete | Typed errors, recovery |

### 2.2 What Needs to Be Built

| Component | Priority | Complexity | Notes |
|-----------|----------|------------|-------|
| **VelHarness API** | P0 | Medium | Main public API wrapper |
| **Middleware System** | P0 | High | Plugin architecture |
| **Skills Loader** | P0 | Medium | YAML frontmatter parsing |
| **Skills Registry** | P0 | Low | Skill management |
| **Subagent Spawner** | P0 | High | Isolated context execution |
| **Agent Registry** | P0 | Low | Typed agent configs |
| **Planning Tools** | P0 | Low | TodoWrite/TodoRead |
| **Filesystem Backend** | P0 | Medium | Already have some tools |
| **Context Management** | P1 | High | Truncation/offload |
| **Sandbox Backend** | P1 | High | Code execution isolation |
| **Config Loader** | P1 | Low | JSON/YAML config |
| **State Persistence** | P1 | Medium | Serialization |

### 2.3 vel-ts Architecture Summary

```
AgentV2 (main entry point)
├── Model Providers (OpenAI, Anthropic, Google)
├── Tool System (ToolSpec, Registry)
├── Hooks (onToolCall, onError, etc.)
├── Guardrails (input/output/tool validation)
├── Context Manager (message history)
├── Streaming (SSE, events)
└── Structured Output (JSON parsing)
```

---

## 3. Component Mapping: Python → TypeScript

### 3.1 Direct Mappings

| Python | TypeScript | Notes |
|--------|------------|-------|
| `VelHarness` | `VelHarness` | Same API |
| `DeepAgent` | (internal) | Wrapped by VelHarness |
| `AgentConfig` | `AgentConfig` | Subagent configuration |
| `AgentRegistry` | `AgentRegistry` | Type registry |
| `Skill` | `Skill` | Skill dataclass |
| `SkillsRegistry` | `SkillsRegistry` | Skill management |
| `ToolSpec` | `ToolSpec` | Already in vel-ts |
| `ModelConfig` | `ModelConfig` | Already in vel-ts |

### 3.2 Pattern Translations

| Python Pattern | TypeScript Pattern |
|----------------|-------------------|
| `Protocol` (structural typing) | `interface` |
| `@dataclass` | `interface` + class or `type` |
| `Optional[T]` | `T \| undefined` or `T?` |
| `Dict[str, Any]` | `Record<string, unknown>` |
| `List[T]` | `T[]` |
| `async def` | `async function` |
| `AsyncIterator` | `AsyncGenerator` |
| `from_dict()` | Constructor or factory function |
| `get_state()/load_state()` | `toJSON()/fromJSON()` |

### 3.3 Middleware Translation

**Python:**
```python
class BaseMiddleware:
    def get_tools(self) -> List[ToolSpec]: ...
    def get_system_prompt_segment(self) -> str: ...
    def get_state(self) -> Dict[str, Any]: ...
    def load_state(self, state: Dict[str, Any]) -> None: ...
```

**TypeScript:**
```typescript
interface Middleware {
  getTools(): ToolSpec[];
  getSystemPromptSegment(): string;
  toJSON(): Record<string, unknown>;
  fromJSON(state: Record<string, unknown>): void;
}

// Abstract base for shared logic
abstract class BaseMiddleware implements Middleware {
  abstract getTools(): ToolSpec[];
  getSystemPromptSegment(): string { return ''; }
  toJSON(): Record<string, unknown> { return {}; }
  fromJSON(state: Record<string, unknown>): void {}
}
```

---

## 4. Gap Analysis

### 4.1 Critical Gaps (Must Build)

| Gap | Description | Effort |
|-----|-------------|--------|
| **Middleware System** | Pluggable capability architecture | 3 days |
| **Skills Loader** | YAML frontmatter Markdown parser | 1 day |
| **Skills Middleware** | Tool result injection | 2 days |
| **Subagent Spawner** | Isolated context execution | 3 days |
| **Agent Registry** | Typed agent configurations | 1 day |
| **Planning Middleware** | TodoWrite with list state | 1 day |
| **VelHarness Wrapper** | Main API surface | 2 days |

### 4.2 Important Gaps (Should Build)

| Gap | Description | Effort |
|-----|-------------|--------|
| **Context Management** | Truncation + offload | 2 days |
| **State Persistence** | Session serialization | 1 day |
| **Config Loader** | JSON/YAML config files | 1 day |
| **Filesystem Backend** | Real filesystem + sandbox | 2 days |

### 4.3 Nice-to-Have Gaps (Can Defer)

| Gap | Description | Effort |
|-----|-------------|--------|
| **Database Backend** | SQL query tools | 2 days |
| **Memory Middleware** | AGENTS.md loading | 1 day |
| **Caching Middleware** | Tool result caching | 1 day |
| **Retry Middleware** | Automatic retry | 1 day |

### 4.4 Already Covered by vel-ts

- Multi-provider abstraction
- Tool system with Zod
- Streaming and events
- Lifecycle hooks
- Message history
- Guardrails
- Prompt templates
- Tool approval callbacks

---

## 5. TypeScript Implementation Strategy

### 5.1 Design Principles

1. **Composition Over Inheritance**: Use interfaces and factories
2. **Type Safety First**: Strong typing with Zod validation
3. **Functional Where Possible**: Pure functions, immutable data
4. **Compatible API**: Match Python VelHarness public API
5. **Leverage vel-ts**: Don't reinvent what exists

### 5.2 Key Differences from Python

| Aspect | Python | TypeScript |
|--------|--------|------------|
| **Typing** | Runtime (dataclass) | Compile-time (interface) |
| **Protocols** | Structural (Protocol) | Structural (interface) |
| **Async** | AsyncIterator | AsyncGenerator |
| **State** | Mutable (load_state) | Immutable (fromJSON returns new) |
| **Config** | from_dict classmethod | Factory function |
| **Middleware** | Class-based | Object/class hybrid |

### 5.3 Architecture Overview

```
vel_harness-ts/
├── VelHarness              # Main public API
│   ├── Uses AgentV2 from vel-ts
│   ├── Composes middleware
│   └── Provides run/runStream
├── Middleware Layer
│   ├── Middleware interface
│   ├── PlanningMiddleware
│   ├── FilesystemMiddleware
│   ├── SkillsMiddleware
│   ├── SubagentsMiddleware
│   └── ContextMiddleware
├── Skills System
│   ├── Skill type
│   ├── SkillLoader
│   └── SkillsRegistry
├── Agents System
│   ├── AgentConfig type
│   ├── AgentRegistry
│   └── SubagentSpawner
├── Backends
│   ├── FilesystemBackend interface
│   ├── RealFilesystemBackend
│   └── SandboxBackend
└── Config
    ├── HarnessConfig type
    └── ConfigLoader
```

---

## 6. Detailed Implementation Plan

### Phase 1: Foundation (Week 1)

#### 1.1 Project Setup
```bash
# Initialize package
mkdir vel_harness-ts && cd vel_harness-ts
npm init
# Add dependencies
npm install vel-ts zod gray-matter glob
npm install -D typescript @types/node vitest
```

#### 1.2 Core Types
```typescript
// src/types/config.ts
export interface HarnessConfig {
  model: ModelConfig;
  skillDirs?: string[];
  customAgents?: Record<string, AgentConfig>;
  systemPrompt?: string;
  maxTurns?: number;
  workingDirectory?: string;
  sandbox?: boolean;
  database?: boolean;
  planning?: boolean;
  memory?: boolean;
}

// src/types/agent.ts
export interface AgentConfig {
  tools: string[];
  maxTurns: number;
  description: string;
  systemPromptAddition?: string;
}

// src/types/skill.ts
export interface Skill {
  name: string;
  description: string;
  content: string;
  triggers: string[];
  tags: string[];
  priority: number;
  enabled: boolean;
  sourcePath?: string;
  author?: string;
  version?: string;
  requires: string[];
}
```

#### 1.3 Middleware Interface
```typescript
// src/middleware/base.ts
export interface Middleware {
  readonly name: string;
  getTools(): ToolSpec[];
  getSystemPromptSegment(): string;
  toJSON(): Record<string, unknown>;
  fromJSON(state: Record<string, unknown>): void;
}

export abstract class BaseMiddleware implements Middleware {
  abstract readonly name: string;
  abstract getTools(): ToolSpec[];

  getSystemPromptSegment(): string {
    return '';
  }

  toJSON(): Record<string, unknown> {
    return {};
  }

  fromJSON(_state: Record<string, unknown>): void {
    // Override in subclasses
  }
}
```

### Phase 2: Skills System (Week 1-2)

#### 2.1 Skill Loader
```typescript
// src/skills/loader.ts
import matter from 'gray-matter';
import { glob } from 'glob';
import { readFile } from 'fs/promises';

export async function loadSkill(path: string): Promise<Skill> {
  const content = await readFile(path, 'utf-8');
  const { data, content: body } = matter(content);

  return {
    name: data.name ?? path,
    description: data.description ?? '',
    content: body,
    triggers: data.triggers ?? [],
    tags: data.tags ?? [],
    priority: data.priority ?? 0,
    enabled: data.enabled ?? true,
    sourcePath: path,
    author: data.author,
    version: data.version,
    requires: data.requires ?? [],
  };
}

export async function loadSkillsFromDirectory(dir: string): Promise<Skill[]> {
  const files = await glob('**/SKILL.md', { cwd: dir });
  return Promise.all(files.map(f => loadSkill(`${dir}/${f}`)));
}
```

#### 2.2 Skills Registry
```typescript
// src/skills/registry.ts
export class SkillsRegistry {
  private skills: Map<string, Skill> = new Map();
  private activeSkills: Set<string> = new Set();

  register(skill: Skill): void {
    this.skills.set(skill.name, skill);
  }

  activate(name: string): boolean {
    if (this.skills.has(name)) {
      this.activeSkills.add(name);
      return true;
    }
    return false;
  }

  deactivate(name: string): boolean {
    return this.activeSkills.delete(name);
  }

  getActive(): Skill[] {
    return Array.from(this.activeSkills)
      .map(name => this.skills.get(name)!)
      .filter(Boolean);
  }

  search(query: string): Skill[] {
    const q = query.toLowerCase();
    return Array.from(this.skills.values()).filter(skill =>
      skill.name.toLowerCase().includes(q) ||
      skill.description.toLowerCase().includes(q) ||
      skill.tags.some(t => t.toLowerCase().includes(q))
    );
  }

  matchTriggers(text: string): Skill[] {
    return Array.from(this.skills.values()).filter(skill =>
      skill.triggers.some(trigger => {
        if (trigger.includes('*')) {
          const regex = new RegExp(trigger.replace('*', '.*'), 'i');
          return regex.test(text);
        }
        return text.toLowerCase().includes(trigger.toLowerCase());
      })
    );
  }
}
```

#### 2.3 Skills Middleware
```typescript
// src/middleware/skills.ts
export enum SkillInjectionMode {
  TOOL_RESULT = 'tool_result',
  SYSTEM_PROMPT = 'system_prompt',
}

export class SkillsMiddleware extends BaseMiddleware {
  readonly name = 'skills';
  private registry: SkillsRegistry;
  private injectionMode: SkillInjectionMode;

  constructor(options: {
    skillDirs?: string[];
    injectionMode?: SkillInjectionMode;
  }) {
    super();
    this.registry = new SkillsRegistry();
    this.injectionMode = options.injectionMode ?? SkillInjectionMode.TOOL_RESULT;
  }

  getTools(): ToolSpec[] {
    return [
      new ToolSpec({
        name: 'list_skills',
        description: 'List available skills',
        inputSchema: z.object({ query: z.string().optional() }),
        handler: async ({ query }) => {
          const skills = query
            ? this.registry.search(query)
            : Array.from(this.registry.getAll());
          return skills.map(s => ({ name: s.name, description: s.description }));
        },
      }),
      new ToolSpec({
        name: 'activate_skill',
        description: 'Activate a skill for the current session',
        inputSchema: z.object({ name: z.string() }),
        handler: async ({ name }) => {
          const activated = this.registry.activate(name);
          if (!activated) return { error: `Skill '${name}' not found` };

          const skill = this.registry.get(name)!;
          return {
            activated: true,
            skill: skill.name,
            content: skill.content, // Injected as tool_result
          };
        },
      }),
      new ToolSpec({
        name: 'deactivate_skill',
        description: 'Deactivate a skill',
        inputSchema: z.object({ name: z.string() }),
        handler: async ({ name }) => {
          return { deactivated: this.registry.deactivate(name) };
        },
      }),
    ];
  }
}
```

### Phase 3: Subagents System (Week 2)

#### 3.1 Agent Registry
```typescript
// src/agents/registry.ts
const DEFAULT_AGENTS: Record<string, AgentConfig> = {
  default: {
    tools: ['execute', 'read_file', 'write_file', 'edit_file',
            'ls', 'glob', 'grep', 'write_todos'],
    maxTurns: 50,
    description: 'General-purpose task execution',
  },
  explore: {
    tools: ['read_file', 'ls', 'glob', 'grep', 'execute'],
    maxTurns: 30,
    description: 'Read-only codebase exploration',
  },
  plan: {
    tools: ['read_file', 'ls', 'glob', 'grep', 'write_todos'],
    maxTurns: 20,
    description: 'Structured planning and task breakdown',
  },
};

export class AgentRegistry {
  private agents: Map<string, AgentConfig>;

  constructor(customAgents?: Record<string, AgentConfig>) {
    this.agents = new Map(Object.entries({
      ...DEFAULT_AGENTS,
      ...customAgents,
    }));
  }

  get(agentId: string): AgentConfig | undefined {
    return this.agents.get(agentId);
  }

  register(agentId: string, config: AgentConfig): void {
    this.agents.set(agentId, config);
  }

  list(): string[] {
    return Array.from(this.agents.keys());
  }

  getDescriptions(): string {
    return Array.from(this.agents.entries())
      .map(([id, config]) => `- ${id}: ${config.description}`)
      .join('\n');
  }
}
```

#### 3.2 Subagent Spawner
```typescript
// src/subagents/spawner.ts
import { AgentV2 } from 'vel-ts';

export enum SubagentStatus {
  PENDING = 'pending',
  RUNNING = 'running',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled',
}

export interface SubagentResult {
  id: string;
  task: string;
  agentType: string;
  status: SubagentStatus;
  result?: string;
  error?: string;
  startedAt?: Date;
  completedAt?: Date;
  messages: LLMMessage[];
}

export class SubagentSpawner {
  private registry: AgentRegistry;
  private model: ModelConfig;
  private maxConcurrent: number;
  private running: Map<string, Promise<SubagentResult>> = new Map();
  private results: Map<string, SubagentResult> = new Map();

  constructor(options: {
    registry: AgentRegistry;
    model: ModelConfig;
    maxConcurrent?: number;
  }) {
    this.registry = options.registry;
    this.model = options.model;
    this.maxConcurrent = options.maxConcurrent ?? 5;
  }

  async spawn(task: string, agentType: string = 'default'): Promise<SubagentResult> {
    const config = this.registry.get(agentType);
    if (!config) {
      throw new Error(`Unknown agent type: ${agentType}`);
    }

    // Check concurrent limit
    if (this.running.size >= this.maxConcurrent) {
      throw new Error('Max concurrent subagents reached');
    }

    const id = crypto.randomUUID();
    const result: SubagentResult = {
      id,
      task,
      agentType,
      status: SubagentStatus.RUNNING,
      startedAt: new Date(),
      messages: [],
    };

    const promise = this.runAgent(result, config);
    this.running.set(id, promise);

    return promise;
  }

  private async runAgent(
    result: SubagentResult,
    config: AgentConfig
  ): Promise<SubagentResult> {
    try {
      const agent = new AgentV2({
        id: `subagent-${result.id}`,
        model: this.model,
        tools: this.getToolsForAgent(config.tools),
        policies: { maxSteps: config.maxTurns },
        systemPrompt: this.buildSystemPrompt(result.agentType, config),
      });

      const response = await agent.run(result.task);

      result.status = SubagentStatus.COMPLETED;
      result.result = response.content;
      result.completedAt = new Date();
    } catch (error) {
      result.status = SubagentStatus.FAILED;
      result.error = error instanceof Error ? error.message : String(error);
      result.completedAt = new Date();
    } finally {
      this.running.delete(result.id);
      this.results.set(result.id, result);
    }

    return result;
  }

  async wait(id: string, timeout: number = 300000): Promise<SubagentResult> {
    const promise = this.running.get(id);
    if (promise) {
      return Promise.race([
        promise,
        new Promise<SubagentResult>((_, reject) =>
          setTimeout(() => reject(new Error('Timeout')), timeout)
        ),
      ]);
    }

    const result = this.results.get(id);
    if (result) return result;

    throw new Error(`Subagent ${id} not found`);
  }

  cancel(id: string): boolean {
    // Mark as cancelled (actual cancellation requires AbortController)
    const result = this.results.get(id);
    if (result && result.status === SubagentStatus.RUNNING) {
      result.status = SubagentStatus.CANCELLED;
      return true;
    }
    return false;
  }
}
```

#### 3.3 Subagents Middleware
```typescript
// src/middleware/subagents.ts
export class SubagentsMiddleware extends BaseMiddleware {
  readonly name = 'subagents';
  private spawner: SubagentSpawner;

  constructor(options: {
    registry: AgentRegistry;
    model: ModelConfig;
    maxConcurrent?: number;
  }) {
    super();
    this.spawner = new SubagentSpawner(options);
  }

  getTools(): ToolSpec[] {
    return [
      new ToolSpec({
        name: 'spawn_subagent',
        description: 'Spawn a subagent for task delegation',
        inputSchema: z.object({
          task: z.string().describe('Task description'),
          agent: z.string().optional().describe('Agent type: default, explore, plan'),
        }),
        handler: async ({ task, agent }) => {
          const result = await this.spawner.spawn(task, agent ?? 'default');
          return {
            id: result.id,
            status: result.status,
            agentType: result.agentType,
          };
        },
      }),
      new ToolSpec({
        name: 'wait_subagent',
        description: 'Wait for a subagent to complete',
        inputSchema: z.object({
          id: z.string(),
          timeout: z.number().optional(),
        }),
        handler: async ({ id, timeout }) => {
          const result = await this.spawner.wait(id, timeout);
          return {
            status: result.status,
            result: result.result,
            error: result.error,
          };
        },
      }),
      new ToolSpec({
        name: 'spawn_parallel',
        description: 'Spawn multiple subagents in parallel',
        inputSchema: z.object({
          tasks: z.array(z.object({
            task: z.string(),
            agent: z.string().optional(),
          })),
        }),
        handler: async ({ tasks }) => {
          const promises = tasks.map(t =>
            this.spawner.spawn(t.task, t.agent ?? 'default')
          );
          const results = await Promise.all(promises);
          return results.map(r => ({
            id: r.id,
            status: r.status,
            agentType: r.agentType,
          }));
        },
      }),
    ];
  }
}
```

### Phase 4: Planning & Filesystem (Week 2-3)

#### 4.1 Planning Middleware
```typescript
// src/middleware/planning.ts
interface TodoItem {
  id: string;
  content: string;
  activeForm: string;
  status: 'pending' | 'in_progress' | 'completed' | 'blocked';
  createdAt: Date;
  updatedAt: Date;
}

export class PlanningMiddleware extends BaseMiddleware {
  readonly name = 'planning';
  private todos: Map<string, TodoItem> = new Map();

  getTools(): ToolSpec[] {
    return [
      new ToolSpec({
        name: 'write_todos',
        description: 'Create or update the todo list',
        inputSchema: z.object({
          todos: z.array(z.object({
            content: z.string(),
            activeForm: z.string(),
            status: z.enum(['pending', 'in_progress', 'completed', 'blocked']),
          })),
        }),
        handler: async ({ todos }) => {
          this.todos.clear();
          for (const todo of todos) {
            const id = crypto.randomUUID();
            this.todos.set(id, {
              id,
              ...todo,
              createdAt: new Date(),
              updatedAt: new Date(),
            });
          }
          return { success: true, count: todos.length };
        },
      }),
      new ToolSpec({
        name: 'read_todos',
        description: 'Read the current todo list',
        inputSchema: z.object({}),
        handler: async () => {
          return Array.from(this.todos.values());
        },
      }),
    ];
  }

  toJSON(): Record<string, unknown> {
    return {
      todos: Array.from(this.todos.entries()),
    };
  }

  fromJSON(state: Record<string, unknown>): void {
    if (state.todos) {
      this.todos = new Map(state.todos as [string, TodoItem][]);
    }
  }
}
```

#### 4.2 Filesystem Middleware
```typescript
// src/middleware/filesystem.ts
import * as fs from 'fs/promises';
import * as path from 'path';
import { glob } from 'glob';

export class FilesystemMiddleware extends BaseMiddleware {
  readonly name = 'filesystem';
  private workingDir: string;

  constructor(workingDir?: string) {
    super();
    this.workingDir = workingDir ?? process.cwd();
  }

  getTools(): ToolSpec[] {
    return [
      new ToolSpec({
        name: 'read_file',
        description: 'Read file contents',
        inputSchema: z.object({
          file_path: z.string(),
          offset: z.number().optional(),
          limit: z.number().optional(),
        }),
        handler: async ({ file_path, offset = 0, limit }) => {
          const fullPath = path.resolve(this.workingDir, file_path);
          const content = await fs.readFile(fullPath, 'utf-8');
          const lines = content.split('\n');
          const selected = limit
            ? lines.slice(offset, offset + limit)
            : lines.slice(offset);

          return {
            content: selected.map((line, i) =>
              `${String(offset + i + 1).padStart(5)}→${line}`
            ).join('\n'),
            totalLines: lines.length,
          };
        },
      }),
      new ToolSpec({
        name: 'write_file',
        description: 'Write content to a file',
        inputSchema: z.object({
          file_path: z.string(),
          content: z.string(),
        }),
        handler: async ({ file_path, content }) => {
          const fullPath = path.resolve(this.workingDir, file_path);
          await fs.mkdir(path.dirname(fullPath), { recursive: true });
          await fs.writeFile(fullPath, content, 'utf-8');
          return { success: true, path: fullPath };
        },
      }),
      new ToolSpec({
        name: 'edit_file',
        description: 'Edit a file by replacing text',
        inputSchema: z.object({
          file_path: z.string(),
          old_string: z.string(),
          new_string: z.string(),
          replace_all: z.boolean().optional(),
        }),
        handler: async ({ file_path, old_string, new_string, replace_all }) => {
          const fullPath = path.resolve(this.workingDir, file_path);
          let content = await fs.readFile(fullPath, 'utf-8');

          if (replace_all) {
            content = content.replaceAll(old_string, new_string);
          } else {
            content = content.replace(old_string, new_string);
          }

          await fs.writeFile(fullPath, content, 'utf-8');
          return { success: true };
        },
      }),
      new ToolSpec({
        name: 'glob',
        description: 'Find files matching a pattern',
        inputSchema: z.object({
          pattern: z.string(),
          path: z.string().optional(),
        }),
        handler: async ({ pattern, path: searchPath }) => {
          const cwd = searchPath
            ? path.resolve(this.workingDir, searchPath)
            : this.workingDir;
          const files = await glob(pattern, { cwd });
          return { files };
        },
      }),
      new ToolSpec({
        name: 'grep',
        description: 'Search file contents',
        inputSchema: z.object({
          pattern: z.string(),
          path: z.string().optional(),
          glob: z.string().optional(),
        }),
        handler: async ({ pattern, path: searchPath, glob: globPattern }) => {
          // Simplified grep implementation
          const cwd = searchPath
            ? path.resolve(this.workingDir, searchPath)
            : this.workingDir;

          const files = await glob(globPattern ?? '**/*', {
            cwd,
            nodir: true,
            ignore: ['node_modules/**', '.git/**'],
          });

          const regex = new RegExp(pattern, 'gi');
          const matches: Array<{ file: string; line: number; content: string }> = [];

          for (const file of files.slice(0, 100)) { // Limit files
            try {
              const content = await fs.readFile(path.join(cwd, file), 'utf-8');
              const lines = content.split('\n');
              lines.forEach((line, i) => {
                if (regex.test(line)) {
                  matches.push({ file, line: i + 1, content: line.trim() });
                }
              });
            } catch {
              // Skip unreadable files
            }
          }

          return { matches: matches.slice(0, 50) }; // Limit matches
        },
      }),
    ];
  }
}
```

### Phase 5: VelHarness Main API (Week 3)

#### 5.1 Main Harness Class
```typescript
// src/harness.ts
import { AgentV2, ToolSpec, ModelConfig } from 'vel-ts';

export class VelHarness {
  private agent: AgentV2;
  private middlewares: Map<string, Middleware> = new Map();
  private agentRegistry: AgentRegistry;
  private config: HarnessConfig;

  constructor(config: HarnessConfig) {
    this.config = config;
    this.agentRegistry = new AgentRegistry(config.customAgents);

    // Initialize middlewares based on config
    this.initializeMiddlewares();

    // Create the underlying agent
    this.agent = new AgentV2({
      id: 'vel-harness',
      model: config.model,
      tools: this.collectTools(),
      systemPrompt: this.buildSystemPrompt(),
      policies: { maxSteps: config.maxTurns ?? 100 },
      hooks: this.buildHooks(),
    });
  }

  private initializeMiddlewares(): void {
    // Always add filesystem
    this.middlewares.set('filesystem', new FilesystemMiddleware(
      this.config.workingDirectory
    ));

    // Planning
    if (this.config.planning !== false) {
      this.middlewares.set('planning', new PlanningMiddleware());
    }

    // Skills
    if (this.config.skillDirs?.length) {
      this.middlewares.set('skills', new SkillsMiddleware({
        skillDirs: this.config.skillDirs,
        injectionMode: SkillInjectionMode.TOOL_RESULT,
      }));
    }

    // Subagents
    this.middlewares.set('subagents', new SubagentsMiddleware({
      registry: this.agentRegistry,
      model: this.config.model,
    }));
  }

  private collectTools(): ToolSpec[] {
    const tools: ToolSpec[] = [];
    for (const middleware of this.middlewares.values()) {
      tools.push(...middleware.getTools());
    }
    return tools;
  }

  private buildSystemPrompt(): string {
    const segments = [
      this.config.systemPrompt ?? DEFAULT_SYSTEM_PROMPT,
    ];

    for (const middleware of this.middlewares.values()) {
      const segment = middleware.getSystemPromptSegment();
      if (segment) segments.push(segment);
    }

    return segments.join('\n\n');
  }

  // Public API matching Python VelHarness

  async run(
    message: string,
    options?: { sessionId?: string; context?: Record<string, unknown> }
  ): Promise<string> {
    const response = await this.agent.run(message, {
      sessionId: options?.sessionId,
      context: options?.context,
    });
    return response.content;
  }

  async *runStream(
    message: string,
    options?: { sessionId?: string; context?: Record<string, unknown> }
  ): AsyncGenerator<StreamEvent> {
    yield* this.agent.runStream(message, {
      sessionId: options?.sessionId,
      context: options?.context,
    });
  }

  registerAgent(agentId: string, config: AgentConfig): void {
    this.agentRegistry.register(agentId, config);
  }

  listAgentTypes(): string[] {
    return this.agentRegistry.list();
  }

  getState(): Record<string, unknown> {
    const state: Record<string, unknown> = {};
    for (const [name, middleware] of this.middlewares) {
      state[name] = middleware.toJSON();
    }
    return state;
  }

  loadState(state: Record<string, unknown>): void {
    for (const [name, middleware] of this.middlewares) {
      if (state[name]) {
        middleware.fromJSON(state[name] as Record<string, unknown>);
      }
    }
  }
}

// Factory functions
export function createHarness(config?: Partial<HarnessConfig>): VelHarness {
  return new VelHarness({
    model: config?.model ?? { provider: 'anthropic', model: 'claude-sonnet-4-5-20250929' },
    ...config,
  });
}

export function createCodingHarness(
  workingDirectory?: string,
  config?: Partial<HarnessConfig>
): VelHarness {
  return createHarness({
    workingDirectory,
    sandbox: true,
    planning: true,
    ...config,
  });
}

export function createResearchHarness(config?: Partial<HarnessConfig>): VelHarness {
  return createHarness({
    sandbox: true,
    planning: true,
    systemPrompt: RESEARCH_SYSTEM_PROMPT,
    ...config,
  });
}
```

---

## 7. Directory Structure

```
vel_harness-ts/
├── package.json
├── tsconfig.json
├── vitest.config.ts
├── README.md
├── src/
│   ├── index.ts                    # Main exports
│   ├── harness.ts                  # VelHarness class
│   ├── types/
│   │   ├── config.ts               # HarnessConfig, etc.
│   │   ├── agent.ts                # AgentConfig
│   │   ├── skill.ts                # Skill type
│   │   └── index.ts
│   ├── middleware/
│   │   ├── base.ts                 # Middleware interface
│   │   ├── planning.ts             # TodoWrite
│   │   ├── filesystem.ts           # File operations
│   │   ├── skills.ts               # Skills middleware
│   │   ├── subagents.ts            # Subagent spawning
│   │   ├── context.ts              # Context management
│   │   └── index.ts
│   ├── skills/
│   │   ├── loader.ts               # YAML frontmatter parsing
│   │   ├── registry.ts             # SkillsRegistry
│   │   └── index.ts
│   ├── agents/
│   │   ├── config.ts               # Default agent configs
│   │   ├── registry.ts             # AgentRegistry
│   │   └── index.ts
│   ├── subagents/
│   │   ├── spawner.ts              # SubagentSpawner
│   │   ├── types.ts                # SubagentResult, etc.
│   │   └── index.ts
│   ├── backends/
│   │   ├── filesystem.ts           # FilesystemBackend interface
│   │   ├── real.ts                 # RealFilesystemBackend
│   │   ├── sandbox.ts              # SandboxBackend (future)
│   │   └── index.ts
│   ├── prompts/
│   │   ├── system.ts               # Default system prompts
│   │   ├── tools.ts                # Tool-specific prompts
│   │   └── index.ts
│   └── config/
│       ├── loader.ts               # Config file loading
│       └── index.ts
├── tests/
│   ├── harness.test.ts
│   ├── skills.test.ts
│   ├── subagents.test.ts
│   ├── middleware.test.ts
│   └── fixtures/
│       └── skills/
│           └── SKILL.md
└── examples/
    ├── basic.ts
    ├── with-skills.ts
    └── subagent-research.ts
```

---

## 8. API Design

### 8.1 Public API Surface

```typescript
// Main entry points
export { VelHarness } from './harness';
export { createHarness, createCodingHarness, createResearchHarness } from './harness';

// Types
export type { HarnessConfig } from './types/config';
export type { AgentConfig } from './types/agent';
export type { Skill } from './types/skill';

// Middleware (for custom extensions)
export type { Middleware } from './middleware/base';
export { BaseMiddleware } from './middleware/base';

// Registries
export { AgentRegistry } from './agents/registry';
export { SkillsRegistry } from './skills/registry';

// Subagents
export { SubagentSpawner } from './subagents/spawner';
export type { SubagentResult } from './subagents/types';

// Skills
export { loadSkill, loadSkillsFromDirectory } from './skills/loader';
```

### 8.2 Usage Examples

```typescript
// Basic usage
import { VelHarness } from 'vel-harness-ts';

const harness = new VelHarness({
  model: { provider: 'anthropic', model: 'claude-sonnet-4-5-20250929' },
  skillDirs: ['./skills'],
  planning: true,
});

// Non-streaming
const response = await harness.run('Analyze the codebase');

// Streaming
for await (const event of harness.runStream('Write a function')) {
  if (event.type === 'text-delta') {
    process.stdout.write(event.delta);
  }
}

// With session
const sessionId = 'user-123';
await harness.run('First message', { sessionId });
await harness.run('Follow up', { sessionId });

// State persistence
const state = harness.getState();
await saveToDatabase(state);
// Later...
harness.loadState(loadedState);
```

---

## 9. Migration Path & Compatibility

### 9.1 API Compatibility

| Python Method | TypeScript Method | Notes |
|---------------|-------------------|-------|
| `run(message, session_id, context)` | `run(message, { sessionId, context })` | Options object |
| `run_stream(...)` | `runStream(...)` | AsyncGenerator |
| `register_agent(id, config)` | `registerAgent(id, config)` | Same |
| `list_agent_types()` | `listAgentTypes()` | Same |
| `get_state()` | `getState()` | Same |
| `load_state(state)` | `loadState(state)` | Same |

### 9.2 Breaking Changes

1. **Options object**: TypeScript uses `{ sessionId, context }` instead of positional args
2. **Stream events**: Uses vel-ts event types (compatible with AI SDK v5)
3. **Config structure**: Some fields renamed for TypeScript conventions

### 9.3 Feature Parity Checklist

| Feature | Python | TypeScript | Status |
|---------|--------|------------|--------|
| VelHarness API | ✅ | 🔲 | To build |
| Skills system | ✅ | 🔲 | To build |
| Subagents | ✅ | 🔲 | To build |
| Planning tools | ✅ | 🔲 | To build |
| Filesystem tools | ✅ | 🔲 | To build |
| Context management | ✅ | 🔲 | To build |
| Sandbox execution | ✅ | 🔲 | Future |
| Database tools | ✅ | 🔲 | Future |
| Memory system | ✅ | 🔲 | Future |

---

## 10. Testing Strategy

### 10.1 Unit Tests

```typescript
// tests/skills.test.ts
import { describe, it, expect } from 'vitest';
import { loadSkill, SkillsRegistry } from '../src/skills';

describe('SkillsRegistry', () => {
  it('should load skills from directory', async () => {
    const registry = new SkillsRegistry();
    await registry.loadFromDirectory('./tests/fixtures/skills');
    expect(registry.list().length).toBeGreaterThan(0);
  });

  it('should activate and deactivate skills', () => {
    const registry = new SkillsRegistry();
    registry.register({ name: 'test', content: '...', /* ... */ });

    expect(registry.activate('test')).toBe(true);
    expect(registry.getActive()).toHaveLength(1);
    expect(registry.deactivate('test')).toBe(true);
    expect(registry.getActive()).toHaveLength(0);
  });

  it('should match triggers', () => {
    const registry = new SkillsRegistry();
    registry.register({
      name: 'sql',
      triggers: ['sql*', 'database', 'query'],
      /* ... */
    });

    const matches = registry.matchTriggers('help with SQL queries');
    expect(matches).toHaveLength(1);
  });
});
```

### 10.2 Integration Tests

```typescript
// tests/harness.test.ts
describe('VelHarness', () => {
  it('should run a simple query', async () => {
    const harness = new VelHarness({
      model: { provider: 'anthropic', model: 'claude-sonnet-4-5-20250929' },
    });

    const response = await harness.run('What is 2+2?');
    expect(response).toContain('4');
  });

  it('should stream responses', async () => {
    const harness = new VelHarness({ /* ... */ });
    const chunks: string[] = [];

    for await (const event of harness.runStream('Count to 3')) {
      if (event.type === 'text-delta') {
        chunks.push(event.delta);
      }
    }

    expect(chunks.join('')).toContain('1');
  });
});
```

### 10.3 Test Fixtures

```markdown
<!-- tests/fixtures/skills/research/SKILL.md -->
---
name: "Research"
description: "Research methodology guidelines"
triggers:
  - "research*"
  - "investigate"
  - "find out"
tags:
  - "research"
  - "methodology"
priority: 10
---

## Research Guidelines

When conducting research:
1. Define the scope clearly
2. Use multiple sources
3. Verify claims
4. Document findings
```

---

## 11. Work Breakdown & Phases

### Phase 1: Foundation (3-4 days)

| Task | Effort | Priority |
|------|--------|----------|
| Project setup (npm, tsconfig, vitest) | 0.5 day | P0 |
| Core types (HarnessConfig, Skill, AgentConfig) | 0.5 day | P0 |
| Middleware interface & base class | 0.5 day | P0 |
| Skills loader (YAML frontmatter) | 1 day | P0 |
| Skills registry | 0.5 day | P0 |
| Basic tests | 0.5 day | P0 |

### Phase 2: Middleware Layer (4-5 days)

| Task | Effort | Priority |
|------|--------|----------|
| Skills middleware (tool result injection) | 1.5 days | P0 |
| Planning middleware (TodoWrite) | 1 day | P0 |
| Filesystem middleware | 1.5 days | P0 |
| Agent registry | 0.5 day | P0 |
| Tests | 0.5 day | P0 |

### Phase 3: Subagents (3-4 days)

| Task | Effort | Priority |
|------|--------|----------|
| SubagentSpawner | 2 days | P0 |
| Subagents middleware | 1 day | P0 |
| Parallel execution | 0.5 day | P0 |
| Tests | 0.5 day | P0 |

### Phase 4: VelHarness API (2-3 days)

| Task | Effort | Priority |
|------|--------|----------|
| VelHarness class | 1.5 days | P0 |
| Factory functions | 0.5 day | P0 |
| State persistence | 0.5 day | P1 |
| Tests & examples | 0.5 day | P0 |

### Phase 5: Polish & Extensions (3-4 days)

| Task | Effort | Priority |
|------|--------|----------|
| Context management middleware | 1.5 days | P1 |
| Config file loading | 0.5 day | P1 |
| System prompts (from Claude Code) | 0.5 day | P1 |
| Documentation | 0.5 day | P1 |
| CI/CD setup | 0.5 day | P1 |

### Future Phases (Post-MVP)

| Task | Effort | Priority |
|------|--------|----------|
| Sandbox execution backend | 2-3 days | P2 |
| Database middleware | 1-2 days | P2 |
| Memory middleware | 1-2 days | P2 |
| Caching middleware | 1 day | P2 |
| Remote sandbox (Modal/Runloop) | 2-3 days | P3 |

---

## Summary

**Total Estimated Effort: 15-20 days**

The TypeScript harness (`vel_harness-ts`) will provide feature parity with the Python version while leveraging vel-ts's existing infrastructure. Key advantages:

1. **Smaller codebase**: vel-ts already provides ~70% of needed functionality
2. **Type safety**: Full TypeScript with Zod validation
3. **Node.js ecosystem**: npm packages for filesystem, YAML parsing, etc.
4. **API compatibility**: Matches Python VelHarness public API
5. **Modern patterns**: AsyncGenerator, composition, interfaces

The implementation follows a phased approach, with core functionality (skills, subagents, planning) in the first 2 weeks, and extensions (context management, sandbox) in subsequent phases.
