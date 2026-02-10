/**
 * Subagents Middleware
 *
 * Provides tools for spawning and managing subagents.
 */

import { ToolSpec } from 'vel-ts';
import type { ModelConfig } from 'vel-ts';
import { z } from 'zod';
import { BaseMiddleware } from './base.js';
import { AgentRegistry } from '../agents/registry.js';
import { SubagentSpawner } from '../subagents/spawner.js';

// Input types
interface SpawnSubagentInput {
  task: string;
  agent?: 'default' | 'explore' | 'plan';
}

interface WaitSubagentInput {
  id: string;
  timeout?: number;
}

interface SpawnParallelInput {
  tasks: Array<{
    task: string;
    agent?: 'default' | 'explore' | 'plan';
  }>;
}

interface GetSubagentResultInput {
  id: string;
}

interface CancelSubagentInput {
  id: string;
}

interface WaitAllSubagentsInput {
  timeout?: number;
}

/**
 * Subagents middleware options
 */
export interface SubagentsMiddlewareOptions {
  /** Agent registry */
  registry: AgentRegistry;

  /** Model configuration for subagents */
  model: ModelConfig;

  /** Maximum concurrent subagents (default: 5) */
  maxConcurrent?: number;

  /** Maximum total subagents per session (default: 10) */
  maxTotalSubagents?: number;

  /** Maximum tasks per spawn_parallel call (default: 5) */
  maxParallelTasks?: number;
}

/**
 * Middleware providing subagent spawning tools
 */
export class SubagentsMiddleware extends BaseMiddleware {
  readonly name = 'subagents';

  private spawner: SubagentSpawner;
  private registry: AgentRegistry;
  private maxTotalSubagents: number;
  private maxParallelTasks: number;
  private totalSpawned = 0;

  constructor(options: SubagentsMiddlewareOptions) {
    super();
    this.registry = options.registry;
    this.maxTotalSubagents = options.maxTotalSubagents ?? 10;
    this.maxParallelTasks = options.maxParallelTasks ?? 5;
    this.spawner = new SubagentSpawner({
      registry: options.registry,
      model: options.model,
      maxConcurrent: options.maxConcurrent ?? 5,
    });
  }

  /**
   * Check if we can spawn more subagents
   */
  private canSpawn(count = 1): { allowed: boolean; reason?: string } {
    if (this.totalSpawned + count > this.maxTotalSubagents) {
      return {
        allowed: false,
        reason: `Subagent limit reached (${this.totalSpawned}/${this.maxTotalSubagents}). Complete your analysis with existing results.`,
      };
    }
    return { allowed: true };
  }

  /**
   * Reset spawn counter (call at session start)
   */
  resetSpawnCount(): void {
    this.totalSpawned = 0;
  }

  /**
   * Get the spawner (for tool injection)
   */
  getSpawner(): SubagentSpawner {
    return this.spawner;
  }

  getTools(): ToolSpec[] {
    const self = this;

    return [
      new ToolSpec<SpawnSubagentInput>({
        name: 'spawn_subagent',
        description: `Spawn a subagent for task delegation. Use sparingly - prefer to do work directly when possible.

Available agent types:
${this.registry.getDescriptions()}`,
        inputSchema: z.object({
          task: z.string().describe('Task description for the subagent'),
          agent: z
            .enum(['default', 'explore', 'plan'])
            .optional()
            .describe('Agent type to use'),
        }),
        requiresConfirmation: true,
        handler: (input: SpawnSubagentInput) => {
          // Check spawn limit
          const check = self.canSpawn(1);
          if (!check.allowed) {
            return { error: check.reason };
          }

          // spawn() is now sync - returns immediately, agent runs in background
          const result = self.spawner.spawn(input.task, input.agent ?? 'default');
          self.totalSpawned++;
          return {
            id: result.id,
            status: result.status,
            agentType: result.agentType,
            remaining: self.maxTotalSubagents - self.totalSpawned,
          };
        },
      }),

      new ToolSpec<WaitSubagentInput>({
        name: 'wait_subagent',
        description: 'Wait for a subagent to complete and get its result',
        inputSchema: z.object({
          id: z.string().describe('Subagent ID'),
          timeout: z.number().optional().describe('Timeout in milliseconds'),
        }),
        requiresConfirmation: true,
        handler: async (input: WaitSubagentInput) => {
          const result = await self.spawner.wait(input.id, input.timeout);
          return {
            id: result.id,
            status: result.status,
            result: result.result,
            error: result.error,
            duration: result.completedAt && result.startedAt
              ? result.completedAt.getTime() - result.startedAt.getTime()
              : undefined,
          };
        },
      }),

      new ToolSpec<WaitAllSubagentsInput>({
        name: 'wait_all_subagents',
        description: 'Wait for ALL running subagents to complete in PARALLEL. Use this after spawn_parallel to get all results at once.',
        inputSchema: z.object({
          timeout: z.number().optional().describe('Timeout in milliseconds (default: 300000)'),
        }),
        requiresConfirmation: true,
        handler: async (input: WaitAllSubagentsInput) => {
          const results = await self.spawner.waitAll(input.timeout);
          return {
            count: results.length,
            results: results.map((r) => ({
              id: r.id,
              task: r.task,
              agentType: r.agentType,
              status: r.status,
              result: r.result,
              error: r.error,
            })),
          };
        },
      }),

      new ToolSpec<SpawnParallelInput>({
        name: 'spawn_parallel',
        description: `Spawn multiple subagents in parallel. Max ${this.maxParallelTasks} tasks per call. Use sparingly.`,
        inputSchema: z.object({
          tasks: z.array(
            z.object({
              task: z.string().describe('Task description'),
              agent: z
                .enum(['default', 'explore', 'plan'])
                .optional()
                .describe('Agent type'),
            })
          ).max(this.maxParallelTasks),
        }),
        requiresConfirmation: true,
        handler: (input: SpawnParallelInput) => {
          // Enforce max tasks per call
          if (input.tasks.length > self.maxParallelTasks) {
            return {
              error: `Too many tasks (${input.tasks.length}). Maximum ${self.maxParallelTasks} per call.`,
            };
          }

          // Check spawn limit
          const check = self.canSpawn(input.tasks.length);
          if (!check.allowed) {
            return { error: check.reason };
          }

          // spawnMany() spawns all in parallel and returns immediately
          const results = self.spawner.spawnMany(
            input.tasks.map((t) => ({ task: t.task, agentType: t.agent }))
          );
          self.totalSpawned += results.length;

          return {
            subagents: results.map((r) => ({
              id: r.id,
              task: r.task,
              agentType: r.agentType,
              status: r.status,
            })),
            count: results.length,
            remaining: self.maxTotalSubagents - self.totalSpawned,
          };
        },
      }),

      new ToolSpec<GetSubagentResultInput>({
        name: 'get_subagent_result',
        description: 'Get the result of a completed subagent',
        inputSchema: z.object({
          id: z.string().describe('Subagent ID'),
        }),
        requiresConfirmation: true,
        handler: async (input: GetSubagentResultInput) => {
          const result = self.spawner.getResult(input.id);
          if (!result) {
            return { error: `Subagent ${input.id} not found` };
          }
          return {
            id: result.id,
            task: result.task,
            agentType: result.agentType,
            status: result.status,
            result: result.result,
            error: result.error,
          };
        },
      }),

      new ToolSpec<CancelSubagentInput>({
        name: 'cancel_subagent',
        description: 'Cancel a running subagent',
        inputSchema: z.object({
          id: z.string().describe('Subagent ID'),
        }),
        handler: async (input: CancelSubagentInput) => {
          const cancelled = self.spawner.cancel(input.id);
          return { cancelled, id: input.id };
        },
      }),
    ] as unknown as ToolSpec[];
  }

  getSystemPromptSegment(): string {
    return `# Subagents

You can delegate tasks to specialized subagents. Use them SPARINGLY - prefer direct tool use when possible.

**Limits**: Max ${this.maxTotalSubagents} subagents per session, max ${this.maxParallelTasks} per spawn_parallel call.

${this.registry.getDescriptions()}

**When to use subagents**:
- Exploring MULTIPLE INDEPENDENT codebases or directories in parallel
- When you need to search many different areas simultaneously
- Complex multi-part research that genuinely benefits from parallelism

**When NOT to use subagents**:
- Simple file reads or searches - use Read/Grep/Glob directly
- Sequential exploration - just do it yourself
- When you already have the information you need
- Iterative deepening - do one round, then decide if more is needed

**Best practices**:
- Spawn subagents ONCE for a task, then work with the results
- Don't spawn more subagents to "analyze" what previous subagents found
- Prefer fewer, well-scoped subagent tasks over many small ones
- After spawn_parallel, call wait_all_subagents to get results`;
  }
}
