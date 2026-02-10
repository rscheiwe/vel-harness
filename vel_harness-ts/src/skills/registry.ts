/**
 * Skills Registry
 *
 * Manages skill loading, activation, and search.
 */

import type { Skill } from '../types/skill.js';
import { loadSkillsFromDirectories } from './loader.js';

/**
 * Registry for managing skills
 */
export class SkillsRegistry {
  private skills: Map<string, Skill> = new Map();
  private activeSkills: Set<string> = new Set();
  private skillDirs: string[];

  constructor(skillDirs: string[] = []) {
    this.skillDirs = skillDirs;
  }

  /**
   * Load skills from configured directories
   */
  async load(): Promise<number> {
    if (this.skillDirs.length === 0) {
      return 0;
    }

    const skills = await loadSkillsFromDirectories(this.skillDirs);
    for (const skill of skills) {
      this.register(skill);
    }

    return skills.length;
  }

  /**
   * Register a skill
   */
  register(skill: Skill): void {
    this.skills.set(skill.name, skill);
  }

  /**
   * Get a skill by name
   */
  get(name: string): Skill | undefined {
    return this.skills.get(name);
  }

  /**
   * Get all registered skills
   */
  getAll(): Skill[] {
    return Array.from(this.skills.values());
  }

  /**
   * List all skill names
   */
  list(): string[] {
    return Array.from(this.skills.keys());
  }

  /**
   * Activate a skill
   */
  activate(name: string): boolean {
    const skill = this.skills.get(name);
    if (!skill) {
      return false;
    }
    this.activeSkills.add(name);
    return true;
  }

  /**
   * Deactivate a skill
   */
  deactivate(name: string): boolean {
    return this.activeSkills.delete(name);
  }

  /**
   * Get all active skills
   */
  getActive(): Skill[] {
    return Array.from(this.activeSkills)
      .map((name) => this.skills.get(name))
      .filter((skill): skill is Skill => skill !== undefined);
  }

  /**
   * Check if a skill is active
   */
  isActive(name: string): boolean {
    return this.activeSkills.has(name);
  }

  /**
   * Search skills by query
   */
  search(query: string): Skill[] {
    const q = query.toLowerCase();
    return Array.from(this.skills.values()).filter(
      (skill) =>
        skill.name.toLowerCase().includes(q) ||
        skill.description.toLowerCase().includes(q) ||
        skill.tags.some((t) => t.toLowerCase().includes(q))
    );
  }

  /**
   * Find skills matching triggers in text
   */
  matchTriggers(text: string): Skill[] {
    const lowerText = text.toLowerCase();
    return Array.from(this.skills.values()).filter((skill) =>
      skill.triggers.some((trigger) => {
        if (trigger.includes('*')) {
          // Convert glob pattern to regex
          const regex = new RegExp(
            trigger.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\\\*/g, '.*'),
            'i'
          );
          return regex.test(lowerText);
        }
        return lowerText.includes(trigger.toLowerCase());
      })
    );
  }

  /**
   * Serialize registry state
   */
  toJSON(): Record<string, unknown> {
    return {
      activeSkills: Array.from(this.activeSkills),
    };
  }

  /**
   * Restore registry state
   */
  fromJSON(state: Record<string, unknown>): void {
    if (Array.isArray(state.activeSkills)) {
      this.activeSkills = new Set(state.activeSkills as string[]);
    }
  }
}
