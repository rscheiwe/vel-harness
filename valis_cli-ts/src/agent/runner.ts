/**
 * Agent Runner
 *
 * Wraps VelHarness and normalizes events for the CLI.
 */

import { randomUUID } from 'crypto';
import { VelHarness, createHarness, ApprovalManager, PendingApproval, SubagentEvent } from 'vel-harness-ts';

// StreamEvent type - simplified for our needs
interface StreamEvent {
  type: string;
  [key: string]: unknown;
}

// Re-export SubagentEvent for UI components
export type { SubagentEvent } from 'vel-harness-ts';
import { EventType, AgentEvent, createEvent } from './events.js';
import type { Config, Message, TokenUsage, Permissions } from '../config/types.js';
import {
  loadPermissions,
  savePermissions,
  checkPermission,
} from '../config/index.js';

export class AgentRunner {
  private harness: VelHarness | null = null;
  private config: Config;
  private sessionId: string;
  private messages: Message[] = [];
  private permissions: Permissions;
  private running = false;

  // Token tracking
  private tokenUsage: TokenUsage = {
    input: 0,
    output: 0,
    total: 0,
    cacheRead: 0,
    cacheCreation: 0,
  };

  // Turn-level tracking
  private currentAssistantText = '';
  private currentToolCalls: Array<{ id: string; name: string; args: Record<string, unknown> }> = [];

  // Streaming tool call tracking
  private streamingToolCall: { id: string; name: string; inputText: string } | null = null;

  // Get the harness's approval manager (set after initialization)
  private approvalManager: ApprovalManager | null = null;

  constructor(config: Config) {
    this.config = config;
    this.sessionId = randomUUID().slice(0, 8);
    this.permissions = loadPermissions(config);
  }

  get isRunning(): boolean {
    return this.running;
  }

  /**
   * Initialize the harness
   */
  async initialize(): Promise<void> {
    if (this.harness) return;

    // Build skill directories
    const skillDirs: string[] = [];

    // Project skills
    if (this.config.projectDir) {
      const projectSkills = `${this.config.projectDir}/skills`;
      skillDirs.push(projectSkills);
    }

    // Global skills
    skillDirs.push(`${this.config.globalDir}/skills`);

    // Create harness
    this.harness = createHarness({
      model: {
        provider: this.config.model.provider,
        model: this.config.model.model,
        ...(this.config.model.temperature !== undefined && {
          temperature: this.config.model.temperature,
        }),
        ...(this.config.model.maxTokens !== undefined && {
          maxTokens: this.config.model.maxTokens,
        }),
      },
      skillDirs,
      maxTurns: this.config.maxTurns,
      workingDirectory: process.cwd(),
      sandbox: this.config.sandboxEnabled,
      planning: true,
      toolApprovalCallback: async () => {
        // Approval is handled by the harness's ApprovalManager
        // This callback just indicates that approval is needed
        return true;
      },
    });

    await this.harness.initialize();

    // Get reference to the harness's approval manager
    this.approvalManager = this.harness.approvalManager;
  }

  /**
   * Run the agent with user input
   */
  async *run(input: string): AsyncGenerator<AgentEvent> {
    await this.initialize();

    if (!this.harness) {
      yield createEvent(EventType.ERROR, { error: 'Agent not initialized' });
      return;
    }

    this.running = true;

    // Reset turn-level tracking
    this.currentAssistantText = '';
    this.currentToolCalls = [];

    // Async queue for merging harness and subagent events
    const eventQueue: AgentEvent[] = [];
    const state = { resolveWaiting: null as (() => void) | null };
    let streamDone = false;

    // Push event to queue and wake up consumer
    const pushEvent = (event: AgentEvent) => {
      eventQueue.push(event);
      if (state.resolveWaiting) {
        const resolver = state.resolveWaiting;
        state.resolveWaiting = null;
        resolver();
      }
    };

    // Subagent event listener
    const subagentListener = (event: SubagentEvent) => {
      const normalized = this.normalizeSubagentEvent(event);
      if (normalized) {
        pushEvent(normalized);
      }
    };

    try {
      // Add user message
      this.messages.push({
        role: 'user',
        content: input,
        timestamp: new Date(),
      });

      yield createEvent(EventType.SESSION_START, { sessionId: this.sessionId });

      // Register subagent event listener
      this.harness.onSubagentEvent(subagentListener);

      // Run harness stream in background, pushing events to queue
      const streamPromise = (async () => {
        try {
          for await (const event of this.harness!.runStream(input, {
            sessionId: this.sessionId,
          })) {
            const normalized = this.normalizeEvent(event as unknown as StreamEvent);
            if (normalized) {
              pushEvent(normalized);
            }
          }
        } finally {
          streamDone = true;
          // Wake up consumer if waiting
          if (state.resolveWaiting) {
            const resolver = state.resolveWaiting;
            state.resolveWaiting = null;
            resolver();
          }
        }
      })();

      // Consume merged event queue
      while (!streamDone || eventQueue.length > 0) {
        // Yield all available events
        while (eventQueue.length > 0) {
          yield eventQueue.shift()!;
        }

        // Wait for more events if stream not done
        if (!streamDone) {
          await new Promise<void>((resolve) => {
            state.resolveWaiting = resolve;
          });
        }
      }

      // Wait for stream to fully complete
      await streamPromise;

      // Finalize turn
      if (this.currentAssistantText) {
        this.messages.push({
          role: 'assistant',
          content: this.currentAssistantText,
          timestamp: new Date(),
        });
      }

      yield createEvent(EventType.SESSION_END, { sessionId: this.sessionId });
    } catch (error) {
      yield createEvent(EventType.ERROR, {
        error: error instanceof Error ? error.message : String(error),
      });
    } finally {
      // Unregister subagent event listener
      this.harness.offSubagentEvent(subagentListener);
      this.running = false;
    }
  }

  /**
   * Normalize streaming events from harness to CLI events
   */
  private normalizeEvent(event: StreamEvent): AgentEvent | null {
    // StreamEvent is a union type - check the type field
    const eventData = event as Record<string, unknown>;
    const eventType = eventData.type as string;

    switch (eventType) {
      case 'text-delta': {
        // vel-ts uses 'textDelta', normalize to 'delta'
        const delta = (eventData.textDelta ?? eventData.delta ?? '') as string;
        this.currentAssistantText += delta;
        return createEvent(EventType.TEXT_DELTA, { delta });
      }

      case 'tool-input-start': {
        // Tool call started - initialize streaming state
        const toolCallId = eventData.toolCallId as string || '';
        const toolName = eventData.toolName as string || 'unknown';
        this.streamingToolCall = { id: toolCallId, name: toolName, inputText: '' };
        return createEvent(EventType.TOOL_CALL, {
          id: toolCallId,
          name: toolName,
          args: {},
          streaming: true,
        });
      }

      case 'tool-input-delta': {
        // Streaming tool input
        const delta = (eventData.inputTextDelta ?? '') as string;
        if (this.streamingToolCall) {
          this.streamingToolCall.inputText += delta;
          return createEvent(EventType.TOOL_INPUT_DELTA, {
            id: this.streamingToolCall.id,
            delta,
            inputText: this.streamingToolCall.inputText,
          });
        }
        return null;
      }

      case 'tool-input-available': {
        const toolCallId = eventData.toolCallId as string || '';
        const toolName = eventData.toolName as string || 'unknown';
        let rawInput = eventData.input;
        // Parse if input is a JSON string
        if (typeof rawInput === 'string') {
          try {
            rawInput = JSON.parse(rawInput);
          } catch {
            rawInput = { raw: rawInput };
          }
        }
        const input = (rawInput as Record<string, unknown>) || {};

        // Clear streaming state
        this.streamingToolCall = null;

        this.currentToolCalls.push({
          id: toolCallId,
          name: toolName,
          args: input,
        });

        // Check permission
        const permission = this.checkToolPermission(toolName, input);

        if (permission === 'deny') {
          return createEvent(EventType.TOOL_CALL, {
            id: toolCallId,
            name: toolName,
            args: input,
            denied: true,
          });
        }

        if (permission === 'ask' || permission === null) {
          return createEvent(EventType.APPROVAL_REQUIRED, {
            id: toolCallId,
            name: toolName,
            args: input,
          });
        }

        return createEvent(EventType.TOOL_CALL, {
          id: toolCallId,
          name: toolName,
          args: input,
          approved: true,
        });
      }

      case 'tool-output-available': {
        const toolCallId = eventData.toolCallId as string || '';
        const output = eventData.output;

        return createEvent(EventType.TOOL_RESULT, {
          id: toolCallId,
          result: output,
        });
      }

      case 'response-metadata': {
        const usage = eventData.usage as Record<string, number> | undefined;
        if (usage) {
          const promptTokens = usage.promptTokens || usage.inputTokens || 0;
          const completionTokens = usage.completionTokens || usage.outputTokens || 0;
          const totalTokens = usage.totalTokens || 0;

          this.tokenUsage.input += promptTokens;
          this.tokenUsage.output += completionTokens;
          this.tokenUsage.total += totalTokens;
          this.tokenUsage.cacheRead += usage.cacheReadTokens || 0;
          this.tokenUsage.cacheCreation += usage.cacheCreationTokens || 0;

          return createEvent(EventType.RESPONSE_METADATA, {
            usage: {
              input: promptTokens,
              output: completionTokens,
              total: totalTokens,
            },
          });
        }
        return null;
      }

      case 'error': {
        const errorText = eventData.errorText as string || 'Unknown error';
        return createEvent(EventType.ERROR, { error: errorText });
      }

      default:
        // Ignore other events (start, finish, etc.)
        return null;
    }
  }

  /**
   * Normalize subagent events from harness to CLI events
   */
  private normalizeSubagentEvent(event: SubagentEvent): AgentEvent | null {
    switch (event.type) {
      case 'subagent-start':
        return createEvent(EventType.SUBAGENT_START, {
          subagentId: event.subagentId,
          agentType: event.agentType,
          task: event.task,
        });

      case 'subagent-event': {
        // Forward the inner stream event with subagent context
        const innerEvent = event.event as Record<string, unknown> | undefined;
        if (!innerEvent) return null;

        // Extract relevant info from inner event
        const eventType = innerEvent.type as string;
        let toolName: string | null = null;
        let toolDescription: string | null = null;
        let isToolStart = false;
        let isToolEnd = false;
        let tokens = 0;

        if (eventType === 'text-delta') {
          // Skip text deltas - they're too noisy
          return null;
        } else if (eventType === 'tool-input-available' || eventType === 'tool-input-start') {
          toolName = innerEvent.toolName as string || 'unknown';
          const input = innerEvent.input as Record<string, unknown> | undefined;

          // Build a descriptive string based on tool and args
          if (toolName === 'Read' || toolName === 'read_file') {
            toolDescription = `Read: ${input?.file_path || input?.path || 'file'}`;
          } else if (toolName === 'Grep' || toolName === 'grep') {
            toolDescription = `Grep: ${input?.pattern || 'pattern'}`;
          } else if (toolName === 'Glob' || toolName === 'glob') {
            toolDescription = `Glob: ${input?.pattern || 'pattern'}`;
          } else if (toolName === 'Bash' || toolName === 'bash') {
            const cmd = (input?.command as string || '').slice(0, 30);
            toolDescription = `Bash: ${cmd}${(input?.command as string || '').length > 30 ? '...' : ''}`;
          } else if (toolName === 'Edit' || toolName === 'edit_file') {
            toolDescription = `Edit: ${input?.file_path || input?.path || 'file'}`;
          } else {
            toolDescription = toolName;
          }
          isToolStart = true;
        } else if (eventType === 'tool-output-available') {
          isToolEnd = true;
        } else if (eventType === 'response-metadata') {
          const usage = innerEvent.usage as Record<string, number> | undefined;
          if (usage) {
            tokens = usage.totalTokens || usage.promptTokens || 0;
          }
        }

        // Only emit for tool starts (most informative)
        if (!isToolStart && !isToolEnd && tokens === 0) {
          return null;
        }

        return createEvent(EventType.SUBAGENT_ACTIVITY, {
          subagentId: event.subagentId,
          agentType: event.agentType,
          task: event.task,
          toolName,
          toolDescription,
          isToolStart,
          isToolEnd,
          tokens,
        });
      }

      case 'subagent-complete':
        return createEvent(EventType.SUBAGENT_COMPLETE, {
          subagentId: event.subagentId,
          agentType: event.agentType,
          task: event.task,
          result: event.result?.result,
        });

      case 'subagent-error':
        return createEvent(EventType.SUBAGENT_ERROR, {
          subagentId: event.subagentId,
          agentType: event.agentType,
          task: event.task,
          error: event.error,
        });

      default:
        return null;
    }
  }

  /**
   * Respond to pending approval (called from UI)
   * @param approved Whether the tool is approved
   * @param toolName The tool name to approve (from APPROVAL_REQUIRED event)
   */
  respondToApproval(approved: boolean, toolName?: string): void {
    if (!this.approvalManager) return;

    if (toolName) {
      // Respond by tool name (handles both pending and pre-stored)
      this.approvalManager.respondByToolName(toolName, approved);
    } else {
      // Respond to first pending approval
      const pending = this.approvalManager.getNext();
      if (pending) {
        this.approvalManager.respond(pending.id, approved);
      }
    }
  }

  /**
   * Check if there's a pending approval
   */
  hasPendingApproval(): boolean {
    return this.approvalManager?.hasPending() ?? false;
  }

  /**
   * Get the next pending approval
   */
  getNextPendingApproval(): PendingApproval | null {
    return this.approvalManager?.getNext() ?? null;
  }

  /**
   * Get all pending approvals
   */
  getAllPendingApprovals(): PendingApproval[] {
    return this.approvalManager?.getPending() ?? [];
  }

  /**
   * Get count of pending approvals
   */
  getPendingApprovalCount(): number {
    return this.approvalManager?.pendingCount ?? 0;
  }

  /**
   * Check tool permission
   */
  checkToolPermission(
    toolName: string,
    args: Record<string, unknown>
  ): 'allow' | 'deny' | 'ask' | null {
    // Check auto-approve list first
    if (this.config.approval.autoApprove.includes(toolName)) {
      return 'allow';
    }

    // Check always deny
    if (this.config.approval.alwaysDeny.includes(toolName)) {
      return 'deny';
    }

    // Check settings.local.json permissions
    return checkPermission(this.permissions, toolName, args);
  }

  /**
   * Grant permission for a tool
   */
  grantPermission(pattern: string, always = false): void {
    if (always) {
      if (!this.permissions.allow.includes(pattern)) {
        this.permissions.allow.push(pattern);
        // Remove from other lists
        this.permissions.deny = this.permissions.deny.filter(p => p !== pattern);
        this.permissions.ask = this.permissions.ask.filter(p => p !== pattern);
      }
      savePermissions(this.config, this.permissions);
    }
  }

  /**
   * Deny permission for a tool
   */
  denyPermission(pattern: string, always = false): void {
    if (always) {
      if (!this.permissions.deny.includes(pattern)) {
        this.permissions.deny.push(pattern);
        // Remove from other lists
        this.permissions.allow = this.permissions.allow.filter(p => p !== pattern);
        this.permissions.ask = this.permissions.ask.filter(p => p !== pattern);
      }
      savePermissions(this.config, this.permissions);
    }
  }

  /**
   * Reset session
   */
  resetSession(): void {
    this.messages = [];
    this.sessionId = randomUUID().slice(0, 8);
    this.currentAssistantText = '';
    this.currentToolCalls = [];
    this.tokenUsage = {
      input: 0,
      output: 0,
      total: 0,
      cacheRead: 0,
      cacheCreation: 0,
    };
  }

  /**
   * Get message history
   */
  getMessageHistory(): Message[] {
    return [...this.messages];
  }

  /**
   * Get last assistant message
   */
  getLastAssistantMessage(): string | null {
    for (let i = this.messages.length - 1; i >= 0; i--) {
      if (this.messages[i].role === 'assistant') {
        return this.messages[i].content;
      }
    }
    return null;
  }

  /**
   * Get token usage
   */
  getTokenUsage(): TokenUsage {
    return { ...this.tokenUsage };
  }

  /**
   * Get permissions
   */
  getPermissions(): Permissions {
    return { ...this.permissions };
  }
}
