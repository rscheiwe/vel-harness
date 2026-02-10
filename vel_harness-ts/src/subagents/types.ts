/**
 * Subagent Types
 */

/**
 * Subagent execution status
 */
export enum SubagentStatus {
  PENDING = 'pending',
  RUNNING = 'running',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled',
}

/**
 * Result from a subagent execution
 */
export interface SubagentResult {
  /** Unique ID for this subagent run */
  id: string;

  /** The task that was given to the subagent */
  task: string;

  /** The agent type used */
  agentType: string;

  /** Current status */
  status: SubagentStatus;

  /** Final result (if completed) */
  result?: string;

  /** Error message (if failed) */
  error?: string;

  /** When execution started */
  startedAt?: Date;

  /** When execution completed */
  completedAt?: Date;

  /** Message history from the subagent */
  messages: unknown[];
}
