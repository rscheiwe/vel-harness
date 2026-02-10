/**
 * Skills System Tests
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { join } from 'node:path';
import { loadSkill, loadSkillsFromDirectory } from '../src/skills/loader.js';
import { SkillsRegistry } from '../src/skills/registry.js';

const FIXTURES_DIR = join(import.meta.dirname, 'fixtures', 'skills');

describe('Skill Loader', () => {
  it('should load a skill from SKILL.md', async () => {
    const skill = await loadSkill(join(FIXTURES_DIR, 'research', 'SKILL.md'));

    expect(skill.name).toBe('Research');
    expect(skill.description).toBe('Research methodology guidelines');
    expect(skill.triggers).toContain('research*');
    expect(skill.tags).toContain('research');
    expect(skill.priority).toBe(10);
    expect(skill.content).toContain('Research Guidelines');
  });

  it('should load skills from directory', async () => {
    const skills = await loadSkillsFromDirectory(FIXTURES_DIR);

    expect(skills.length).toBeGreaterThan(0);
    expect(skills[0].name).toBe('Research');
  });
});

describe('Skills Registry', () => {
  let registry: SkillsRegistry;

  beforeEach(() => {
    registry = new SkillsRegistry();
  });

  it('should register and retrieve skills', () => {
    registry.register({
      name: 'test',
      description: 'Test skill',
      content: 'Test content',
      triggers: [],
      tags: [],
      priority: 0,
      enabled: true,
      requires: [],
    });

    const skill = registry.get('test');
    expect(skill).toBeDefined();
    expect(skill?.name).toBe('test');
  });

  it('should activate and deactivate skills', () => {
    registry.register({
      name: 'test',
      description: 'Test skill',
      content: 'Test content',
      triggers: [],
      tags: [],
      priority: 0,
      enabled: true,
      requires: [],
    });

    expect(registry.activate('test')).toBe(true);
    expect(registry.isActive('test')).toBe(true);
    expect(registry.getActive()).toHaveLength(1);

    expect(registry.deactivate('test')).toBe(true);
    expect(registry.isActive('test')).toBe(false);
    expect(registry.getActive()).toHaveLength(0);
  });

  it('should match triggers', () => {
    registry.register({
      name: 'sql',
      description: 'SQL skill',
      content: 'SQL content',
      triggers: ['sql*', 'database', 'query'],
      tags: [],
      priority: 0,
      enabled: true,
      requires: [],
    });

    const matches = registry.matchTriggers('help with SQL queries');
    expect(matches).toHaveLength(1);
    expect(matches[0].name).toBe('sql');
  });

  it('should search skills', () => {
    registry.register({
      name: 'python',
      description: 'Python programming guidelines',
      content: 'Python content',
      triggers: [],
      tags: ['programming', 'python'],
      priority: 0,
      enabled: true,
      requires: [],
    });

    const results = registry.search('python');
    expect(results).toHaveLength(1);

    const tagResults = registry.search('programming');
    expect(tagResults).toHaveLength(1);
  });

  it('should serialize and restore state', () => {
    registry.register({
      name: 'test',
      description: 'Test skill',
      content: 'Test content',
      triggers: [],
      tags: [],
      priority: 0,
      enabled: true,
      requires: [],
    });

    registry.activate('test');

    const state = registry.toJSON();
    expect(state.activeSkills).toContain('test');

    const newRegistry = new SkillsRegistry();
    newRegistry.register({
      name: 'test',
      description: 'Test skill',
      content: 'Test content',
      triggers: [],
      tags: [],
      priority: 0,
      enabled: true,
      requires: [],
    });
    newRegistry.fromJSON(state);

    expect(newRegistry.isActive('test')).toBe(true);
  });
});
