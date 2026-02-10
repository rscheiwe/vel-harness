/**
 * Middleware Base Types
 *
 * Middleware are pluggable capabilities that provide tools and system prompt segments.
 */

import type { ToolSpec } from 'vel-ts';

/**
 * Middleware interface defining pluggable capabilities
 */
export interface Middleware {
  /** Unique middleware name */
  readonly name: string;

  /**
   * Get tools provided by this middleware
   */
  getTools(): ToolSpec[];

  /**
   * Get system prompt segment for this middleware
   */
  getSystemPromptSegment(): string;

  /**
   * Serialize middleware state for persistence
   */
  toJSON(): Record<string, unknown>;

  /**
   * Restore middleware state from persistence
   */
  fromJSON(state: Record<string, unknown>): void;
}

/**
 * Abstract base class for middleware implementations
 */
export abstract class BaseMiddleware implements Middleware {
  abstract readonly name: string;

  /**
   * Get tools provided by this middleware.
   * Subclasses must implement this.
   */
  abstract getTools(): ToolSpec[];

  /**
   * Get system prompt segment.
   * Override in subclasses that need prompt additions.
   */
  getSystemPromptSegment(): string {
    return '';
  }

  /**
   * Serialize state for persistence.
   * Override in subclasses with state.
   */
  toJSON(): Record<string, unknown> {
    return {};
  }

  /**
   * Restore state from persistence.
   * Override in subclasses with state.
   */
  fromJSON(_state: Record<string, unknown>): void {
    // Override in subclasses
  }
}

/**
 * Middleware registry for composing multiple middlewares
 */
export class MiddlewareRegistry {
  private middlewares: Map<string, Middleware> = new Map();

  /**
   * Register a middleware
   */
  register(middleware: Middleware): void {
    this.middlewares.set(middleware.name, middleware);
  }

  /**
   * Get a middleware by name
   */
  get(name: string): Middleware | undefined {
    return this.middlewares.get(name);
  }

  /**
   * Get all registered middlewares
   */
  getAll(): Middleware[] {
    return Array.from(this.middlewares.values());
  }

  /**
   * Collect all tools from all middlewares
   */
  collectTools(): ToolSpec[] {
    const tools: ToolSpec[] = [];
    for (const middleware of this.middlewares.values()) {
      tools.push(...middleware.getTools());
    }
    return tools;
  }

  /**
   * Build combined system prompt from all middlewares
   */
  buildSystemPrompt(basePrompt: string): string {
    const segments = [basePrompt];
    for (const middleware of this.middlewares.values()) {
      const segment = middleware.getSystemPromptSegment();
      if (segment) {
        segments.push(segment);
      }
    }
    return segments.join('\n\n');
  }

  /**
   * Serialize all middleware state
   */
  toJSON(): Record<string, Record<string, unknown>> {
    const state: Record<string, Record<string, unknown>> = {};
    for (const [name, middleware] of this.middlewares) {
      state[name] = middleware.toJSON();
    }
    return state;
  }

  /**
   * Restore all middleware state
   */
  fromJSON(state: Record<string, Record<string, unknown>>): void {
    for (const [name, middlewareState] of Object.entries(state)) {
      const middleware = this.middlewares.get(name);
      if (middleware) {
        middleware.fromJSON(middlewareState);
      }
    }
  }
}
