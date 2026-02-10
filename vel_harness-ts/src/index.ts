/**
 * vel-harness-ts - TypeScript Agent Harness
 *
 * Claude Code-style capabilities built on vel-ts runtime.
 */

// =========================
// Main Entry Point
// =========================
export { VelHarness } from './harness.js';
export type { PendingApproval } from './harness.js';

// =========================
// Approval Management
// =========================
export { ApprovalManager } from './approval/manager.js';

// =========================
// Factory Functions
// =========================
export {
  createHarness,
  createResearchHarness,
  createCodingHarness,
  createMinimalHarness,
} from './factory.js';

// =========================
// Types
// =========================
export type {
  HarnessConfig,
  RunOptions,
  ToolApprovalCallback,
} from './types/config.js';

export type { SubagentConfig } from './types/agent.js';
export { DEFAULT_AGENTS } from './types/agent.js';

export type { Skill, SkillFrontmatter } from './types/skill.js';
export { SkillInjectionMode } from './types/skill.js';

// =========================
// Middleware
// =========================
export type { Middleware } from './middleware/base.js';
export { BaseMiddleware, MiddlewareRegistry } from './middleware/base.js';
export { FilesystemMiddleware } from './middleware/filesystem.js';
export { PlanningMiddleware } from './middleware/planning.js';
export type { TodoItem, TodoStatus } from './middleware/planning.js';
export { SkillsMiddleware } from './middleware/skills.js';
export { SubagentsMiddleware } from './middleware/subagents.js';

// =========================
// Skills
// =========================
export { loadSkill, loadSkillsFromDirectory, loadSkillsFromDirectories } from './skills/loader.js';
export { SkillsRegistry } from './skills/registry.js';

// =========================
// Agents
// =========================
export { AgentRegistry } from './agents/registry.js';

// =========================
// Subagents
// =========================
export { SubagentSpawner } from './subagents/spawner.js';
export type { SubagentEvent } from './subagents/spawner.js';
export { SubagentStatus } from './subagents/types.js';
export type { SubagentResult } from './subagents/types.js';

// =========================
// Prompts
// =========================
export {
  DEFAULT_SYSTEM_PROMPT,
  RESEARCH_SYSTEM_PROMPT,
  CODING_SYSTEM_PROMPT,
} from './prompts/system.js';

// =========================
// Version
// =========================
export const VERSION = '0.1.0';
