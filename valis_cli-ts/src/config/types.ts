/**
 * Configuration Types
 */

export interface ModelSettings {
  provider: string;
  model: string;
  temperature?: number;
  maxTokens?: number;
}

export interface ApprovalSettings {
  requireApproval: boolean;
  autoApprove: string[];
  alwaysDeny: string[];
}

export interface Permissions {
  allow: string[];
  deny: string[];
  ask: string[];
}

export interface Config {
  globalDir: string;
  projectDir?: string;
  model: ModelSettings;
  approval: ApprovalSettings;
  agentName: string;
  maxTurns: number;
  sandboxEnabled: boolean;
  showThinking: boolean;
  showToolCalls: boolean;
  compactMode: boolean;
}

export interface TokenUsage {
  input: number;
  output: number;
  total: number;
  cacheRead: number;
  cacheCreation: number;
}

export interface Message {
  role: 'user' | 'assistant' | 'system' | 'error' | 'tool';
  content: string;
  timestamp?: Date;
  metadata?: Record<string, unknown>;
}

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
  pending: boolean;
  result?: unknown;
  error?: string;
  inputText?: string;  // Streaming input text (raw JSON)
  streaming?: boolean; // True while input is being streamed
}

export interface ToolApproval {
  id: string;
  name: string;
  args: Record<string, unknown>;
}

/**
 * Content block for interleaved text/tool display.
 * Ensures proper ordering: text → tool → text → tool → ...
 */
export type ContentBlock =
  | { type: 'text'; content: string; streaming?: boolean }
  | { type: 'tool'; toolCall: ToolCall };

/**
 * Unified chat item - can be a message or content block.
 * Allows single ordered array for entire conversation.
 */
export type ChatItem =
  | { kind: 'user'; content: string; timestamp?: Date }
  | { kind: 'assistant-text'; content: string; streaming?: boolean }
  | { kind: 'tool'; toolCall: ToolCall }
  | { kind: 'system'; content: string; timestamp?: Date }
  | { kind: 'error'; content: string; timestamp?: Date };
