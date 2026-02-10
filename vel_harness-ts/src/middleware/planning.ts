/**
 * Planning Middleware
 *
 * Provides TodoWrite and TodoRead tools for task tracking.
 */

import { ToolSpec } from 'vel-ts';
import { z } from 'zod';
import { BaseMiddleware } from './base.js';

/**
 * Todo item status
 */
export type TodoStatus = 'pending' | 'in_progress' | 'completed' | 'blocked';

/**
 * A todo item
 */
export interface TodoItem {
  id: string;
  content: string;
  activeForm: string;
  status: TodoStatus;
  createdAt: string;
  updatedAt: string;
}

// Input types
interface WriteTodosInput {
  todos: Array<{
    content: string;
    activeForm: string;
    status: TodoStatus;
  }>;
}

type ReadTodosInput = Record<string, never>;

/**
 * Middleware providing todo/planning tools
 */
export class PlanningMiddleware extends BaseMiddleware {
  readonly name = 'planning';

  private todos: Map<string, TodoItem> = new Map();

  getTools(): ToolSpec[] {
    const self = this;

    return [
      new ToolSpec<WriteTodosInput>({
        name: 'write_todos',
        description:
          'Create or update the todo list. Use this to plan and track tasks.',
        inputSchema: z.object({
          todos: z.array(
            z.object({
              content: z.string().describe('Task description (imperative form)'),
              activeForm: z.string().describe('Present continuous form for status display'),
              status: z
                .enum(['pending', 'in_progress', 'completed', 'blocked'])
                .describe('Task status'),
            })
          ),
        }),
        handler: async (input: WriteTodosInput) => {
          self.todos.clear();
          const now = new Date().toISOString();

          for (const todo of input.todos) {
            const id = crypto.randomUUID();
            self.todos.set(id, {
              id,
              content: todo.content,
              activeForm: todo.activeForm,
              status: todo.status,
              createdAt: now,
              updatedAt: now,
            });
          }

          return {
            success: true,
            count: input.todos.length,
            todos: Array.from(self.todos.values()).map((t) => ({
              content: t.content,
              status: t.status,
            })),
          };
        },
      }),

      new ToolSpec<ReadTodosInput>({
        name: 'read_todos',
        description: 'Read the current todo list',
        inputSchema: z.object({}),
        handler: async () => {
          const todos = Array.from(self.todos.values());
          return {
            todos: todos.map((t) => ({
              content: t.content,
              activeForm: t.activeForm,
              status: t.status,
            })),
            summary: {
              total: todos.length,
              pending: todos.filter((t) => t.status === 'pending').length,
              in_progress: todos.filter((t) => t.status === 'in_progress').length,
              completed: todos.filter((t) => t.status === 'completed').length,
              blocked: todos.filter((t) => t.status === 'blocked').length,
            },
          };
        },
      }),
    ] as unknown as ToolSpec[];
  }

  getSystemPromptSegment(): string {
    return `# Task Management

You have access to todo list tools for planning and tracking tasks:
- Use write_todos to create or update the task list
- Use read_todos to check current task status
- Mark tasks as in_progress before starting work
- Mark tasks as completed immediately after finishing`;
  }

  /**
   * Get current todos (for display)
   */
  getTodos(): TodoItem[] {
    return Array.from(this.todos.values());
  }

  /**
   * Get the currently active task
   */
  getActiveTask(): TodoItem | undefined {
    return Array.from(this.todos.values()).find((t) => t.status === 'in_progress');
  }

  toJSON(): Record<string, unknown> {
    return {
      todos: Array.from(this.todos.entries()),
    };
  }

  fromJSON(state: Record<string, unknown>): void {
    if (Array.isArray(state.todos)) {
      this.todos = new Map(state.todos as [string, TodoItem][]);
    }
  }
}
