/**
 * Filesystem Middleware
 *
 * Provides file operation tools: read, write, edit, glob, grep.
 */

import { readFile, writeFile, mkdir, readdir, stat } from 'node:fs/promises';
import { resolve, dirname, relative } from 'node:path';
import { glob } from 'glob';
import { ToolSpec } from 'vel-ts';
import { z } from 'zod';
import { BaseMiddleware } from './base.js';

// Input type definitions
interface ReadFileInput {
  file_path: string;
  offset?: number;
  limit?: number;
}

interface WriteFileInput {
  file_path: string;
  content: string;
}

interface EditFileInput {
  file_path: string;
  old_string: string;
  new_string: string;
  replace_all?: boolean;
}

interface LsInput {
  path?: string;
}

interface GlobInput {
  pattern: string;
  path?: string;
}

interface GrepInput {
  pattern: string;
  path?: string;
  glob?: string;
  max_results?: number;
}

/**
 * Filesystem middleware options
 */
export interface FilesystemMiddlewareOptions {
  /** Base working directory */
  workingDirectory?: string;
}

/**
 * Middleware providing filesystem tools
 */
export class FilesystemMiddleware extends BaseMiddleware {
  readonly name = 'filesystem';

  private workingDir: string;

  constructor(options: FilesystemMiddlewareOptions = {}) {
    super();
    this.workingDir = options.workingDirectory ?? process.cwd();
  }

  private resolvePath(path: string): string {
    return resolve(this.workingDir, path);
  }

  getTools(): ToolSpec[] {
    const self = this;

    return [
      new ToolSpec<ReadFileInput>({
        name: 'read_file',
        description: 'Read file contents with line numbers',
        inputSchema: z.object({
          file_path: z.string().describe('Path to the file'),
          offset: z.number().optional().describe('Starting line number (0-indexed)'),
          limit: z.number().optional().describe('Number of lines to read'),
        }),
        handler: async (input: ReadFileInput) => {
          const { file_path, offset = 0, limit } = input;
          const fullPath = self.resolvePath(file_path);
          const content = await readFile(fullPath, 'utf-8');
          const lines = content.split('\n');

          const selected = limit
            ? lines.slice(offset, offset + limit)
            : lines.slice(offset);

          const formatted = selected
            .map((line, i) => `${String(offset + i + 1).padStart(5)}→${line}`)
            .join('\n');

          return {
            content: formatted,
            totalLines: lines.length,
            startLine: offset + 1,
            endLine: offset + selected.length,
          };
        },
      }),

      new ToolSpec<WriteFileInput>({
        name: 'write_file',
        description: 'Write content to a file (creates directories if needed)',
        requiresConfirmation: true,
        inputSchema: z.object({
          file_path: z.string().describe('Path to the file'),
          content: z.string().describe('Content to write'),
        }),
        handler: async (input: WriteFileInput) => {
          const { file_path, content } = input;
          const fullPath = self.resolvePath(file_path);
          await mkdir(dirname(fullPath), { recursive: true });
          await writeFile(fullPath, content, 'utf-8');
          return { success: true, path: fullPath };
        },
      }),

      new ToolSpec<EditFileInput>({
        name: 'edit_file',
        description: 'Edit a file by replacing text',
        requiresConfirmation: true,
        inputSchema: z.object({
          file_path: z.string().describe('Path to the file'),
          old_string: z.string().describe('Text to find'),
          new_string: z.string().describe('Text to replace with'),
          replace_all: z.boolean().optional().describe('Replace all occurrences'),
        }),
        handler: async (input: EditFileInput) => {
          const { file_path, old_string, new_string, replace_all } = input;
          const fullPath = self.resolvePath(file_path);
          let content = await readFile(fullPath, 'utf-8');

          if (!content.includes(old_string)) {
            return { error: 'old_string not found in file' };
          }

          if (replace_all) {
            content = content.replaceAll(old_string, new_string);
          } else {
            content = content.replace(old_string, new_string);
          }

          await writeFile(fullPath, content, 'utf-8');
          return { success: true };
        },
      }),

      new ToolSpec<LsInput>({
        name: 'ls',
        description: 'List directory contents',
        inputSchema: z.object({
          path: z.string().optional().describe('Directory path (default: current)'),
        }),
        handler: async (input: LsInput) => {
          const fullPath = self.resolvePath(input.path ?? '.');
          const entries = await readdir(fullPath, { withFileTypes: true });

          const items = await Promise.all(
            entries.map(async (entry) => {
              const itemPath = resolve(fullPath, entry.name);
              let size: number | undefined;
              if (entry.isFile()) {
                const stats = await stat(itemPath);
                size = stats.size;
              }
              return {
                name: entry.name,
                type: entry.isDirectory() ? 'directory' : 'file',
                size,
              };
            })
          );

          return { path: fullPath, items };
        },
      }),

      new ToolSpec<GlobInput>({
        name: 'glob',
        description: 'Find files matching a pattern',
        inputSchema: z.object({
          pattern: z.string().describe('Glob pattern (e.g., **/*.ts)'),
          path: z.string().optional().describe('Base directory'),
        }),
        handler: async (input: GlobInput) => {
          const { pattern, path: basePath } = input;
          const cwd = basePath ? self.resolvePath(basePath) : self.workingDir;
          const files = await glob(pattern, {
            cwd,
            ignore: ['node_modules/**', '.git/**', 'dist/**'],
          });

          return {
            files: files.slice(0, 100),
            count: files.length,
            truncated: files.length > 100,
          };
        },
      }),

      new ToolSpec<GrepInput>({
        name: 'grep',
        description: 'Search file contents with regex',
        inputSchema: z.object({
          pattern: z.string().describe('Search pattern (regex)'),
          path: z.string().optional().describe('Base directory'),
          glob: z.string().optional().describe('File pattern to search'),
          max_results: z.number().optional().describe('Maximum results'),
        }),
        handler: async (input: GrepInput) => {
          const { pattern, path: basePath, glob: globPattern, max_results } = input;
          const cwd = basePath ? self.resolvePath(basePath) : self.workingDir;
          const filePattern = globPattern ?? '**/*';
          const maxResults = max_results ?? 50;

          const files = await glob(filePattern, {
            cwd,
            nodir: true,
            ignore: ['node_modules/**', '.git/**', 'dist/**', '*.lock'],
          });

          const regex = new RegExp(pattern, 'gi');
          const matches: Array<{ file: string; line: number; content: string }> = [];

          for (const file of files.slice(0, 100)) {
            if (matches.length >= maxResults) break;

            try {
              const filePath = resolve(cwd, file);
              const content = await readFile(filePath, 'utf-8');
              const lines = content.split('\n');

              for (let i = 0; i < lines.length && matches.length < maxResults; i++) {
                if (regex.test(lines[i])) {
                  matches.push({
                    file: relative(self.workingDir, filePath),
                    line: i + 1,
                    content: lines[i].trim().slice(0, 200),
                  });
                }
                regex.lastIndex = 0;
              }
            } catch {
              // Skip unreadable files
            }
          }

          return {
            matches,
            count: matches.length,
            truncated: matches.length >= maxResults,
          };
        },
      }),
    ] as unknown as ToolSpec[];
  }

  getSystemPromptSegment(): string {
    return `# File Operations

Working directory: ${this.workingDir}

Available file tools:
- read_file: Read file with line numbers
- write_file: Write content to file
- edit_file: Replace text in file
- ls: List directory contents
- glob: Find files by pattern
- grep: Search file contents`;
  }
}
