/**
 * Harness Configuration Types
 */

import type { ModelConfig, GenerationConfig } from 'vel-ts';
import type { SubagentConfig } from './agent.js';

/**
 * Main harness configuration
 */
export interface HarnessConfig {
  /** Model configuration */
  model: ModelConfig;

  /** Directories containing SKILL.md files */
  skillDirs?: string[];

  /** Custom agent type configurations */
  customAgents?: Record<string, SubagentConfig>;

  /** Override default system prompt (use sparingly - breaks caching) */
  systemPrompt?: string;

  /** Maximum tool-use iterations (default: 100) */
  maxTurns?: number;

  /** Base directory for file operations */
  workingDirectory?: string;

  /** Enable sandboxed code execution (default: true) */
  sandbox?: boolean;

  /** Enable database access (default: false) */
  database?: boolean;

  /** Enable planning/todo tools (default: true) */
  planning?: boolean;

  /** Enable memory middleware (default: false) */
  memory?: boolean;

  /** Subagent limits */
  subagents?: {
    /** Maximum concurrent subagents (default: 5) */
    maxConcurrent?: number;
    /** Maximum total subagents per session (default: 10) */
    maxTotal?: number;
    /** Maximum tasks per spawn_parallel call (default: 5) */
    maxParallelTasks?: number;
  };

  /** Generation config overrides */
  generationConfig?: GenerationConfig;

  /** Tool approval callback for HITL */
  toolApprovalCallback?: ToolApprovalCallback;
}

/**
 * Tool approval callback for human-in-the-loop
 */
export type ToolApprovalCallback = (
  toolName: string,
  args: Record<string, unknown>
) => Promise<boolean>;

/**
 * Run options for individual runs
 */
export interface RunOptions {
  /** Session ID for context continuity */
  sessionId?: string;

  /** Additional context for the run */
  context?: Record<string, unknown>;

  /** Override generation config */
  generationConfig?: GenerationConfig;

  /** Metadata to pass to tools */
  metadata?: Record<string, unknown>;
}
