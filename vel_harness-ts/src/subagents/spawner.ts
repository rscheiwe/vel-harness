/**
 * Subagent Spawner
 *
 * Manages spawning and tracking of subagents with event streaming.
 */

import { EventEmitter } from 'events';
import { AgentV2 } from 'vel-ts';
import type { ModelConfig, ToolSpec, StreamEvent } from 'vel-ts';
import { AgentRegistry } from '../agents/registry.js';
import { SubagentStatus, SubagentResult } from './types.js';

/** Events emitted by subagents */
export interface SubagentEvent {
  type: 'subagent-start' | 'subagent-event' | 'subagent-complete' | 'subagent-error';
  subagentId: string;
  agentType: string;
  task: string;
  event?: StreamEvent;
  result?: SubagentResult;
  error?: string;
}

/**
 * Spawner options
 */
export interface SubagentSpawnerOptions {
  /** Agent registry for type lookups */
  registry: AgentRegistry;

  /** Model configuration */
  model: ModelConfig;

  /** Maximum concurrent subagents */
  maxConcurrent?: number;

  /** Available tools by name */
  availableTools?: Map<string, ToolSpec>;
}

/**
 * Spawns and manages subagent execution with event streaming
 */
export class SubagentSpawner extends EventEmitter {
  private registry: AgentRegistry;
  private model: ModelConfig;
  private maxConcurrent: number;
  private availableTools: Map<string, ToolSpec>;

  private running: Map<string, Promise<SubagentResult>> = new Map();
  private results: Map<string, SubagentResult> = new Map();

  constructor(options: SubagentSpawnerOptions) {
    super();
    this.registry = options.registry;
    this.model = options.model;
    this.maxConcurrent = options.maxConcurrent ?? 5;
    this.availableTools = options.availableTools ?? new Map();
  }

  /** Emit a subagent event */
  private emitSubagentEvent(event: SubagentEvent): void {
    this.emit('subagent-event', event);
  }

  /**
   * Set available tools (for late binding)
   */
  setTools(tools: Map<string, ToolSpec>): void {
    this.availableTools = tools;
  }

  /**
   * Spawn a subagent - returns immediately, runs in background
   * Use wait() to get the result when needed.
   */
  spawn(task: string, agentType: string = 'default'): SubagentResult {
    const config = this.registry.get(agentType);
    if (!config) {
      throw new Error(`Unknown agent type: ${agentType}. Available: ${this.registry.list().join(', ')}`);
    }

    // Check concurrent limit
    if (this.running.size >= this.maxConcurrent) {
      throw new Error(`Max concurrent subagents reached (${this.maxConcurrent})`);
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

    // Start running in background - don't await!
    const promise = this.runAgent(result, config);
    this.running.set(id, promise);

    // Return immediately with the initial result (status: RUNNING)
    return result;
  }

  /**
   * Spawn multiple subagents in parallel
   */
  spawnMany(tasks: Array<{ task: string; agentType?: string }>): SubagentResult[] {
    return tasks.map(({ task, agentType }) => this.spawn(task, agentType ?? 'default'));
  }

  /**
   * Wait for all running subagents to complete
   */
  async waitAll(timeout: number = 300000): Promise<SubagentResult[]> {
    const promises = Array.from(this.running.values());
    if (promises.length === 0) {
      return Array.from(this.results.values());
    }

    const results = await Promise.race([
      Promise.all(promises),
      new Promise<SubagentResult[]>((_, reject) =>
        setTimeout(() => reject(new Error(`Subagents timeout after ${timeout}ms`)), timeout)
      ),
    ]);

    return results;
  }

  private async runAgent(
    result: SubagentResult,
    config: { tools: string[]; maxTurns: number; systemPromptAddition?: string }
  ): Promise<SubagentResult> {
    // Emit start event
    this.emitSubagentEvent({
      type: 'subagent-start',
      subagentId: result.id,
      agentType: result.agentType,
      task: result.task,
    });

    try {
      // Resolve tool names to ToolSpec instances
      const tools: ToolSpec[] = [];
      for (const toolName of config.tools) {
        const tool = this.availableTools.get(toolName);
        if (tool) {
          tools.push(tool);
        }
      }

      // Build system prompt
      let systemPrompt = `You are a ${result.agentType} subagent. Complete the given task.`;
      if (config.systemPromptAddition) {
        systemPrompt += `\n\n${config.systemPromptAddition}`;
      }

      const agent = new AgentV2({
        id: `subagent-${result.id}`,
        model: this.model,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        tools: tools as any,
        policies: { maxSteps: config.maxTurns },
        systemPrompt,
      });

      // Use streaming to emit events as subagent runs
      let finalOutput = '';
      for await (const event of agent.runStream(result.task)) {
        // Emit each event tagged with subagent info
        this.emitSubagentEvent({
          type: 'subagent-event',
          subagentId: result.id,
          agentType: result.agentType,
          task: result.task,
          event: event as StreamEvent,
        });

        // Accumulate text output
        const eventAny = event as unknown as Record<string, unknown>;
        if (eventAny.type === 'text-delta' && eventAny.textDelta) {
          finalOutput += String(eventAny.textDelta);
        }
      }

      result.status = SubagentStatus.COMPLETED;
      result.result = finalOutput;
      result.completedAt = new Date();

      // Emit completion event
      this.emitSubagentEvent({
        type: 'subagent-complete',
        subagentId: result.id,
        agentType: result.agentType,
        task: result.task,
        result,
      });
    } catch (error) {
      result.status = SubagentStatus.FAILED;
      result.error = error instanceof Error ? error.message : String(error);
      result.completedAt = new Date();

      // Emit error event
      this.emitSubagentEvent({
        type: 'subagent-error',
        subagentId: result.id,
        agentType: result.agentType,
        task: result.task,
        error: result.error,
      });
    } finally {
      this.running.delete(result.id);
      this.results.set(result.id, result);
    }

    return result;
  }

  /**
   * Wait for a subagent to complete
   */
  async wait(id: string, timeout: number = 300000): Promise<SubagentResult> {
    const promise = this.running.get(id);
    if (promise) {
      return Promise.race([
        promise,
        new Promise<SubagentResult>((_, reject) =>
          setTimeout(() => reject(new Error(`Subagent timeout after ${timeout}ms`)), timeout)
        ),
      ]);
    }

    const result = this.results.get(id);
    if (result) {
      return result;
    }

    throw new Error(`Subagent ${id} not found`);
  }

  /**
   * Get result of a completed subagent
   */
  getResult(id: string): SubagentResult | undefined {
    return this.results.get(id);
  }

  /**
   * List active subagents
   */
  listActive(): string[] {
    return Array.from(this.running.keys());
  }

  /**
   * Cancel a running subagent
   */
  cancel(id: string): boolean {
    // Note: Full cancellation would require AbortController integration
    const result = this.results.get(id);
    if (result && result.status === SubagentStatus.RUNNING) {
      result.status = SubagentStatus.CANCELLED;
      result.completedAt = new Date();
      return true;
    }
    return false;
  }

  /**
   * Get all results
   */
  getAllResults(): SubagentResult[] {
    return Array.from(this.results.values());
  }
}
