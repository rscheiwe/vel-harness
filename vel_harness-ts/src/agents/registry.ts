/**
 * Agent Registry
 *
 * Manages typed subagent configurations.
 */

import { SubagentConfig, DEFAULT_AGENTS } from '../types/agent.js';

/**
 * Registry for managing subagent type configurations
 */
export class AgentRegistry {
  private agents: Map<string, SubagentConfig>;

  constructor(customAgents?: Record<string, SubagentConfig>) {
    this.agents = new Map(
      Object.entries({
        ...DEFAULT_AGENTS,
        ...customAgents,
      })
    );
  }

  /**
   * Get an agent configuration by ID
   */
  get(agentId: string): SubagentConfig | undefined {
    return this.agents.get(agentId);
  }

  /**
   * Register a custom agent type
   */
  register(agentId: string, config: SubagentConfig): void {
    this.agents.set(agentId, config);
  }

  /**
   * List all agent type IDs
   */
  list(): string[] {
    return Array.from(this.agents.keys());
  }

  /**
   * Check if an agent type exists
   */
  has(agentId: string): boolean {
    return this.agents.has(agentId);
  }

  /**
   * Get formatted descriptions of all agents
   */
  getDescriptions(): string {
    return Array.from(this.agents.entries())
      .map(([id, config]) => `- ${id}: ${config.description}`)
      .join('\n');
  }

  /**
   * Get all agent configurations
   */
  getAll(): Record<string, SubagentConfig> {
    return Object.fromEntries(this.agents);
  }
}
