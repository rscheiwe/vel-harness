/**
 * Agent Event Types
 */

export enum EventType {
  TEXT_START = 'text-start',
  TEXT_DELTA = 'text-delta',
  TEXT_END = 'text-end',
  TOOL_CALL = 'tool-call',
  TOOL_INPUT_DELTA = 'tool-input-delta',
  TOOL_RESULT = 'tool-result',
  THINKING_START = 'thinking-start',
  THINKING_DELTA = 'thinking-delta',
  THINKING_END = 'thinking-end',
  APPROVAL_REQUIRED = 'approval-required',
  APPROVAL_RESPONSE = 'approval-response',
  SESSION_START = 'session-start',
  SESSION_END = 'session-end',
  ERROR = 'error',
  RESPONSE_METADATA = 'response-metadata',
  // Subagent events
  SUBAGENT_START = 'subagent-start',
  SUBAGENT_ACTIVITY = 'subagent-activity',
  SUBAGENT_COMPLETE = 'subagent-complete',
  SUBAGENT_ERROR = 'subagent-error',
}

export interface AgentEvent {
  type: EventType;
  data: Record<string, unknown>;
  timestamp: string;
}

export function createEvent(
  type: EventType,
  data: Record<string, unknown> = {}
): AgentEvent {
  return {
    type,
    data,
    timestamp: new Date().toISOString(),
  };
}
