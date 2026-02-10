/**
 * Skill Types
 *
 * Skills are procedural knowledge loaded from SKILL.md files.
 */

/**
 * A skill definition loaded from SKILL.md
 */
export interface Skill {
  /** Unique skill name */
  name: string;

  /** Human-readable description */
  description: string;

  /** Full markdown content (body after frontmatter) */
  content: string;

  /** Patterns that trigger auto-activation */
  triggers: string[];

  /** Categorization tags */
  tags: string[];

  /** Ordering priority (higher = more important) */
  priority: number;

  /** Whether the skill is currently enabled */
  enabled: boolean;

  /** Path to the source file */
  sourcePath?: string;

  /** Author information */
  author?: string;

  /** Version string */
  version?: string;

  /** Skill dependencies */
  requires: string[];
}

/**
 * YAML frontmatter structure in SKILL.md files
 */
export interface SkillFrontmatter {
  name?: string;
  description?: string;
  triggers?: string[];
  tags?: string[];
  priority?: number;
  enabled?: boolean;
  author?: string;
  version?: string;
  requires?: string[];
}

/**
 * Skill injection modes
 */
export enum SkillInjectionMode {
  /** Skills returned as tool_result (recommended - preserves prompt caching) */
  TOOL_RESULT = 'tool_result',
  /** Skills added to system prompt (legacy - breaks caching) */
  SYSTEM_PROMPT = 'system_prompt',
}
