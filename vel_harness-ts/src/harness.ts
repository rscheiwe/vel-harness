/**
 * VelHarness - Main Entry Point
 *
 * Claude Code-style agent harness built on vel-ts runtime.
 */

import { AgentV2 } from 'vel-ts';
import type { ModelConfig, ToolSpec, StreamEvent } from 'vel-ts';
import type { HarnessConfig, RunOptions } from './types/config.js';
import type { SubagentConfig } from './types/agent.js';
import { MiddlewareRegistry, Middleware } from './middleware/base.js';
import { FilesystemMiddleware } from './middleware/filesystem.js';
import { PlanningMiddleware } from './middleware/planning.js';
import { SkillsMiddleware } from './middleware/skills.js';
import { SubagentsMiddleware } from './middleware/subagents.js';
import { AgentRegistry } from './agents/registry.js';
import { DEFAULT_SYSTEM_PROMPT } from './prompts/system.js';
import { ApprovalManager } from './approval/manager.js';
import type { SubagentEvent } from './subagents/spawner.js';
export type { PendingApproval } from './approval/manager.js';
export type { SubagentEvent } from './subagents/spawner.js';

/**
 * VelHarness - Claude Code-style agent harness
 *
 * Provides:
 * - Skills system with tool_result injection
 * - Subagent spawning (explore, plan, default)
 * - Planning tools (TodoWrite)
 * - File operation tools
 * - Context management
 */
export class VelHarness {
  private agent: AgentV2 | null = null;
  private middlewares: MiddlewareRegistry;
  private agentRegistry: AgentRegistry;
  private config: HarnessConfig;
  private initialized = false;

  /** Approval manager for parallel tool approvals */
  readonly approvalManager: ApprovalManager;

  constructor(config: HarnessConfig) {
    this.config = config;
    this.middlewares = new MiddlewareRegistry();
    this.agentRegistry = new AgentRegistry(config.customAgents);
    this.approvalManager = new ApprovalManager();
  }

  /**
   * Initialize the harness (loads skills, sets up agent)
   */
  async initialize(): Promise<void> {
    if (this.initialized) return;

    // Initialize middlewares
    await this.initializeMiddlewares();

    // Collect all tools
    const tools = this.middlewares.collectTools();

    // Build tool map for subagent spawner
    const toolMap = new Map<string, ToolSpec>();
    for (const tool of tools) {
      toolMap.set(tool.name, tool);
    }

    // Inject tools into subagent spawner
    const subagentsMiddleware = this.middlewares.get('subagents') as SubagentsMiddleware | undefined;
    if (subagentsMiddleware) {
      subagentsMiddleware.getSpawner().setTools(toolMap);
    }

    // Build system prompt
    const systemPrompt = this.middlewares.buildSystemPrompt(
      this.config.systemPrompt ?? DEFAULT_SYSTEM_PROMPT
    );

    // Create the underlying agent
    // Wrap the approval callback with the manager for parallel support
    const approvalCallback = this.config.toolApprovalCallback
      ? async (toolName: string, args: Record<string, unknown>) => {
          return this.approvalManager.requestApproval(toolName, args);
        }
      : undefined;

    this.agent = new AgentV2({
      id: 'vel-harness',
      model: this.config.model,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      tools: tools as any,
      systemPrompt,
      policies: { maxSteps: this.config.maxTurns ?? 100 },
      generationConfig: this.config.generationConfig,
      toolApprovalCallback: approvalCallback,
    });

    this.initialized = true;
  }

  private async initializeMiddlewares(): Promise<void> {
    // Filesystem middleware
    this.middlewares.register(
      new FilesystemMiddleware({
        workingDirectory: this.config.workingDirectory,
      })
    );

    // Planning middleware
    if (this.config.planning !== false) {
      this.middlewares.register(new PlanningMiddleware());
    }

    // Skills middleware
    if (this.config.skillDirs?.length) {
      const skillsMiddleware = new SkillsMiddleware({
        skillDirs: this.config.skillDirs,
      });
      await skillsMiddleware.initialize();
      this.middlewares.register(skillsMiddleware);
    }

    // Subagents middleware
    this.middlewares.register(
      new SubagentsMiddleware({
        registry: this.agentRegistry,
        model: this.config.model,
        maxConcurrent: this.config.subagents?.maxConcurrent,
        maxTotalSubagents: this.config.subagents?.maxTotal,
        maxParallelTasks: this.config.subagents?.maxParallelTasks,
      })
    );
  }

  /**
   * Run agent (non-streaming)
   */
  async run(message: string, options?: RunOptions): Promise<string> {
    await this.initialize();

    if (!this.agent) {
      throw new Error('Agent not initialized');
    }

    // Reset subagent spawn counter for this turn
    const subagentsMiddleware = this.middlewares.get('subagents') as SubagentsMiddleware | undefined;
    subagentsMiddleware?.resetSpawnCount();

    // Check for skill auto-activation
    const skillsMiddleware = this.middlewares.get('skills') as SkillsMiddleware | undefined;
    if (skillsMiddleware) {
      skillsMiddleware.checkAutoActivation(message);
    }

    const response = await this.agent.run(message, {
      sessionId: options?.sessionId,
      context: options?.context,
      generationConfig: options?.generationConfig,
      metadata: options?.metadata,
    });

    return String(response.output);
  }

  /**
   * Run agent with streaming
   */
  async *runStream(
    message: string,
    options?: RunOptions
  ): AsyncGenerator<StreamEvent, void, unknown> {
    await this.initialize();

    if (!this.agent) {
      throw new Error('Agent not initialized');
    }

    // Reset subagent spawn counter for this turn
    const subagentsMiddleware = this.middlewares.get('subagents') as SubagentsMiddleware | undefined;
    subagentsMiddleware?.resetSpawnCount();

    // Check for skill auto-activation
    const skillsMiddleware = this.middlewares.get('skills') as SkillsMiddleware | undefined;
    if (skillsMiddleware) {
      skillsMiddleware.checkAutoActivation(message);
    }

    yield* this.agent.runStream(message, {
      sessionId: options?.sessionId,
      context: options?.context,
      generationConfig: options?.generationConfig,
      metadata: options?.metadata,
    });
  }

  /**
   * Register a custom agent type
   */
  registerAgent(agentId: string, config: SubagentConfig): void {
    this.agentRegistry.register(agentId, config);
  }

  /**
   * List available agent types
   */
  listAgentTypes(): string[] {
    return this.agentRegistry.list();
  }

  /**
   * Get harness state for persistence
   */
  getState(): Record<string, unknown> {
    return this.middlewares.toJSON();
  }

  /**
   * Load harness state from persistence
   */
  loadState(state: Record<string, Record<string, unknown>>): void {
    this.middlewares.fromJSON(state);
  }

  /**
   * Get the model configuration
   */
  get model(): ModelConfig {
    return this.config.model;
  }

  /**
   * Get the agent registry
   */
  getAgentRegistry(): AgentRegistry {
    return this.agentRegistry;
  }

  /**
   * Get a middleware by name
   */
  getMiddleware<T extends Middleware>(name: string): T | undefined {
    return this.middlewares.get(name) as T | undefined;
  }

  /**
   * Register a listener for subagent events.
   * Must be called after initialize().
   */
  onSubagentEvent(listener: (event: SubagentEvent) => void): void {
    const subagentsMiddleware = this.middlewares.get('subagents') as SubagentsMiddleware | undefined;
    if (subagentsMiddleware) {
      subagentsMiddleware.getSpawner().on('subagent-event', listener);
    }
  }

  /**
   * Remove a subagent event listener.
   */
  offSubagentEvent(listener: (event: SubagentEvent) => void): void {
    const subagentsMiddleware = this.middlewares.get('subagents') as SubagentsMiddleware | undefined;
    if (subagentsMiddleware) {
      subagentsMiddleware.getSpawner().off('subagent-event', listener);
    }
  }
}
