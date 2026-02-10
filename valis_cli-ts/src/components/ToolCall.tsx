/**
 * Tool Call Widget
 */

import React from 'react';
import { Box, Text } from 'ink';
import type { ToolCall } from '../config/types.js';

interface ToolCallWidgetProps {
  toolCall: ToolCall;
}

export const ToolCallWidget: React.FC<ToolCallWidgetProps> = ({ toolCall }) => {

  // Parse args if they're a string
  const getArgs = (): Record<string, unknown> => {
    let args = toolCall.args;
    if (typeof args === 'string') {
      try {
        args = JSON.parse(args);
      } catch {
        return { raw: args };
      }
    }
    return (args as Record<string, unknown>) || {};
  };

  const formatArgs = (): string => {
    const name = toolCall.name;
    const args = getArgs();

    // Special formatting for subagent tools
    if (name === 'spawn_subagent' && args.task) {
      const task = String(args.task);
      const agent = args.agent || 'default';
      const preview = task.length > 40 ? task.slice(0, 37) + '...' : task;
      return `[${agent}] "${preview}"`;
    }
    if (name === 'wait_subagent' && args.id) {
      return `id=${String(args.id).slice(0, 12)}...`;
    }
    if (name === 'spawn_parallel' && args.tasks) {
      const tasks = args.tasks as Array<{ task: string }>;
      return `${tasks.length} tasks`;
    }
    if (name === 'wait_all_subagents') {
      return 'all running';
    }

    // Default formatting
    return Object.entries(args)
      .map(([k, v]) => {
        let str: string;
        if (typeof v === 'object' && v !== null) {
          str = JSON.stringify(v);
        } else {
          str = String(v);
        }
        const display = str.length > 50 ? str.slice(0, 47) + '...' : str;
        return `${k}=${display}`;
      })
      .join(', ');
  };

  const formatResult = (): string => {
    if (!toolCall.result) return 'Done';

    if (toolCall.error) {
      return `Error: ${toolCall.error.slice(0, 40)}`;
    }

    const result = toolCall.result;

    // Handle string results (common for file reads, shell output)
    if (typeof result === 'string') {
      const lines = result.split('\n').length;
      const chars = result.length;
      if (lines > 1) {
        return `Read ${lines} lines (${formatBytes(chars)})`;
      } else if (chars > 0) {
        return chars > 60 ? result.slice(0, 57) + '...' : result;
      }
      return 'Done';
    }

    // Handle object results
    if (typeof result === 'object' && result !== null) {
      const r = result as Record<string, unknown>;

      // Error cases
      if (r.error) return `Error: ${String(r.error).slice(0, 40)}`;

      // Subagent-specific results
      if (r.id && r.agentType && r.status) {
        // spawn_subagent result
        return `Spawned ${r.agentType} agent (${String(r.id).slice(0, 8)}...)`;
      }
      if (r.subagents && Array.isArray(r.subagents)) {
        // spawn_parallel result
        return `Spawned ${r.subagents.length} agents in parallel`;
      }
      if (r.results && Array.isArray(r.results)) {
        // wait_all_subagents result
        const completed = (r.results as Array<{status: string}>).filter(
          (x) => x.status === 'completed'
        ).length;
        return `${completed}/${r.results.length} subagents completed`;
      }
      if (r.result && r.status === 'completed') {
        // wait_subagent or get_subagent_result
        const preview = String(r.result).slice(0, 40);
        return preview.length < String(r.result).length ? preview + '...' : preview;
      }

      // Common result patterns
      if (typeof r.count === 'number') return `Found ${r.count} items`;
      if (typeof r.lines === 'number') return `${r.lines} lines`;
      if (typeof r.matches === 'number') return `${r.matches} matches`;
      if (typeof r.files === 'number') return `${r.files} files`;
      if (r.status) return String(r.status);

      // Content with metadata
      if (typeof r.content === 'string') {
        const lines = r.content.split('\n').length;
        return `Read ${lines} lines`;
      }

      // Array results (file lists, search results)
      if (Array.isArray(r.items)) return `${r.items.length} items`;
      if (Array.isArray(r.files)) return `${r.files.length} files`;

      // Output/stdout for shell commands
      if (typeof r.output === 'string' && r.output.length > 0) {
        const preview = r.output.split('\n')[0];
        return preview.length > 50 ? preview.slice(0, 47) + '...' : preview;
      }
      if (typeof r.stdout === 'string' && r.stdout.length > 0) {
        const lines = r.stdout.split('\n').filter(Boolean).length;
        return `${lines} lines output`;
      }
    }

    return 'Done';
  };

  const formatBytes = (bytes: number): string => {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  };

  // Streaming input - show tool name and input as it comes in
  if (toolCall.streaming && toolCall.inputText) {
    const preview = toolCall.inputText.length > 80
      ? toolCall.inputText.slice(0, 77) + '...'
      : toolCall.inputText;
    return (
      <Box paddingX={1} flexDirection="column">
        <Text>
          <Text color="yellow">⋯ </Text>
          <Text color="cyan">{toolCall.name}</Text>
          <Text dimColor>(</Text>
        </Text>
        <Text dimColor>  {preview}</Text>
      </Box>
    );
  }

  if (toolCall.pending) {
    return (
      <Box paddingX={1}>
        <Text color="cyan">⋯ Running {toolCall.name}...</Text>
      </Box>
    );
  }

  return (
    <Box paddingX={1} flexDirection="column">
      <Text>
        <Text color="green">● </Text>
        <Text color="cyan" dimColor>
          {toolCall.name}({formatArgs()})
        </Text>
      </Text>
      <Text dimColor>  └ {formatResult()}</Text>
    </Box>
  );
};
