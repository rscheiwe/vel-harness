/**
 * Skills Middleware
 *
 * Provides skill activation and management tools.
 * Skills are injected as tool_result to preserve prompt caching.
 */

import { ToolSpec } from 'vel-ts';
import { z } from 'zod';
import { BaseMiddleware } from './base.js';
import { SkillsRegistry } from '../skills/registry.js';
import { SkillInjectionMode } from '../types/skill.js';

// Input types
interface ListSkillsInput {
  query?: string;
}

interface ActivateSkillInput {
  name: string;
}

interface DeactivateSkillInput {
  name: string;
}

interface GetSkillInput {
  name: string;
}

/**
 * Skills middleware options
 */
export interface SkillsMiddlewareOptions {
  /** Directories containing SKILL.md files */
  skillDirs?: string[];

  /** Skill injection mode (default: TOOL_RESULT) */
  injectionMode?: SkillInjectionMode;

  /** Auto-activate skills based on triggers */
  autoActivate?: boolean;
}

/**
 * Middleware providing skill management tools
 */
export class SkillsMiddleware extends BaseMiddleware {
  readonly name = 'skills';

  private registry: SkillsRegistry;
  private injectionMode: SkillInjectionMode;
  private autoActivate: boolean;
  private initialized = false;

  constructor(options: SkillsMiddlewareOptions = {}) {
    super();
    this.registry = new SkillsRegistry(options.skillDirs ?? []);
    this.injectionMode = options.injectionMode ?? SkillInjectionMode.TOOL_RESULT;
    this.autoActivate = options.autoActivate ?? true;
  }

  /**
   * Initialize skills (load from directories)
   */
  async initialize(): Promise<void> {
    if (!this.initialized) {
      await this.registry.load();
      this.initialized = true;
    }
  }

  /**
   * Get the skills registry
   */
  getRegistry(): SkillsRegistry {
    return this.registry;
  }

  getTools(): ToolSpec[] {
    const self = this;

    return [
      new ToolSpec<ListSkillsInput>({
        name: 'list_skills',
        description: 'List available skills. Use query to search.',
        inputSchema: z.object({
          query: z.string().optional().describe('Search query for filtering skills'),
        }),
        handler: async (input: ListSkillsInput) => {
          const skills = input.query
            ? self.registry.search(input.query)
            : self.registry.getAll();

          return {
            skills: skills.map((s) => ({
              name: s.name,
              description: s.description,
              tags: s.tags,
              active: self.registry.isActive(s.name),
            })),
            count: skills.length,
          };
        },
      }),

      new ToolSpec<ActivateSkillInput>({
        name: 'activate_skill',
        description:
          'Activate a skill for the current session. The skill content will be returned.',
        inputSchema: z.object({
          name: z.string().describe('Name of the skill to activate'),
        }),
        handler: async (input: ActivateSkillInput) => {
          const activated = self.registry.activate(input.name);
          if (!activated) {
            return { error: `Skill '${input.name}' not found` };
          }

          const skill = self.registry.get(input.name);
          if (!skill) {
            return { error: `Skill '${input.name}' not found` };
          }

          return {
            activated: true,
            skill: skill.name,
            description: skill.description,
            content: skill.content,
          };
        },
      }),

      new ToolSpec<DeactivateSkillInput>({
        name: 'deactivate_skill',
        description: 'Deactivate a skill',
        inputSchema: z.object({
          name: z.string().describe('Name of the skill to deactivate'),
        }),
        handler: async (input: DeactivateSkillInput) => {
          const deactivated = self.registry.deactivate(input.name);
          return { deactivated, skill: input.name };
        },
      }),

      new ToolSpec<GetSkillInput>({
        name: 'get_skill',
        description: 'Get the content of a specific skill without activating it',
        inputSchema: z.object({
          name: z.string().describe('Name of the skill'),
        }),
        handler: async (input: GetSkillInput) => {
          const skill = self.registry.get(input.name);
          if (!skill) {
            return { error: `Skill '${input.name}' not found` };
          }

          return {
            name: skill.name,
            description: skill.description,
            content: skill.content,
            tags: skill.tags,
            triggers: skill.triggers,
            active: self.registry.isActive(skill.name),
          };
        },
      }),
    ] as unknown as ToolSpec[];
  }

  getSystemPromptSegment(): string {
    if (this.injectionMode === SkillInjectionMode.SYSTEM_PROMPT) {
      const activeSkills = this.registry.getActive();
      if (activeSkills.length === 0) {
        return '';
      }

      const segments = activeSkills.map(
        (skill) => `## Skill: ${skill.name}\n\n${skill.content}`
      );
      return `# Active Skills\n\n${segments.join('\n\n---\n\n')}`;
    }

    return '';
  }

  /**
   * Check if any skills should be auto-activated for given input
   */
  checkAutoActivation(input: string): string[] {
    if (!this.autoActivate) {
      return [];
    }

    const matchingSkills = this.registry.matchTriggers(input);
    const activated: string[] = [];

    for (const skill of matchingSkills) {
      if (!this.registry.isActive(skill.name)) {
        this.registry.activate(skill.name);
        activated.push(skill.name);
      }
    }

    return activated;
  }

  toJSON(): Record<string, unknown> {
    return this.registry.toJSON();
  }

  fromJSON(state: Record<string, unknown>): void {
    this.registry.fromJSON(state);
  }
}
