/**
 * Subagent Configuration Types
 */

/**
 * Configuration for a subagent type
 */
export interface SubagentConfig {
  /** Tools available to this agent type */
  tools: string[];

  /** Maximum turns/steps for this agent */
  maxTurns: number;

  /** Human-readable description */
  description: string;

  /** Additional system prompt content */
  systemPromptAddition?: string;
}

/**
 * Default agent types matching Python implementation
 */
export const DEFAULT_AGENTS: Record<string, SubagentConfig> = {
  default: {
    tools: [
      'execute',
      'read_file',
      'write_file',
      'edit_file',
      'ls',
      'glob',
      'grep',
      'write_todos',
    ],
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
