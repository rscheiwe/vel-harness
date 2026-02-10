/**
 * Skill Loader
 *
 * Load skills from SKILL.md files with YAML frontmatter.
 */

import { readFile } from 'node:fs/promises';
import { basename, dirname, join } from 'node:path';
import { glob } from 'glob';
import matter from 'gray-matter';
import type { Skill, SkillFrontmatter } from '../types/skill.js';

/**
 * Load a skill from a SKILL.md file
 */
export async function loadSkill(path: string): Promise<Skill> {
  const content = await readFile(path, 'utf-8');
  const { data, content: body } = matter(content);
  const frontmatter = data as SkillFrontmatter;

  // Derive name from directory if not specified
  const dirName = basename(dirname(path));
  const name = frontmatter.name ?? dirName;

  return {
    name,
    description: frontmatter.description ?? '',
    content: body.trim(),
    triggers: frontmatter.triggers ?? [],
    tags: frontmatter.tags ?? [],
    priority: frontmatter.priority ?? 0,
    enabled: frontmatter.enabled ?? true,
    sourcePath: path,
    author: frontmatter.author,
    version: frontmatter.version,
    requires: frontmatter.requires ?? [],
  };
}

/**
 * Load all skills from a directory
 */
export async function loadSkillsFromDirectory(dir: string): Promise<Skill[]> {
  const pattern = '**/SKILL.md';
  const files = await glob(pattern, {
    cwd: dir,
    absolute: false,
  });

  const skills: Skill[] = [];
  for (const file of files) {
    try {
      const skill = await loadSkill(join(dir, file));
      skills.push(skill);
    } catch (error) {
      console.error(`Failed to load skill from ${file}:`, error);
    }
  }

  // Sort by priority (descending)
  skills.sort((a, b) => b.priority - a.priority);

  return skills;
}

/**
 * Load skills from multiple directories
 */
export async function loadSkillsFromDirectories(dirs: string[]): Promise<Skill[]> {
  const allSkills: Skill[] = [];
  const seenNames = new Set<string>();

  for (const dir of dirs) {
    const skills = await loadSkillsFromDirectory(dir);
    for (const skill of skills) {
      // Skip duplicates (first directory wins)
      if (!seenNames.has(skill.name)) {
        seenNames.add(skill.name);
        allSkills.push(skill);
      }
    }
  }

  return allSkills;
}
