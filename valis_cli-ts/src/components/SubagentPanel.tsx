/**
 * Subagent Panel - Claude Code-style
 *
 * Shows running subagents in a compact, informative format:
 * - Header: "Running N [type] agents... (ctrl+o to expand)"
 * - Each agent: task · tool uses · tokens
 * - Most recent tool activity per agent
 */

import React from 'react';
import { Box, Text } from 'ink';

export interface SubagentInfo {
  id: string;
  agentType: string;
  task: string;
  toolCount: number;
  tokenCount: number;
  currentTool: string | null;
  status: 'running' | 'complete' | 'error';
}

interface SubagentPanelProps {
  subagents: SubagentInfo[];
  expanded?: boolean;
}

export const SubagentPanel: React.FC<SubagentPanelProps> = ({
  subagents,
  expanded = true,
}) => {
  if (subagents.length === 0) {
    return null;
  }

  // Group by agent type for header
  const typeGroups = new Map<string, SubagentInfo[]>();
  for (const agent of subagents) {
    const list = typeGroups.get(agent.agentType) || [];
    list.push(agent);
    typeGroups.set(agent.agentType, list);
  }

  const runningCount = subagents.filter((s) => s.status === 'running').length;

  const formatTokens = (tokens: number): string => {
    if (tokens >= 1000) {
      return `${(tokens / 1000).toFixed(1)}k`;
    }
    return String(tokens);
  };

  const truncateTask = (task: string, maxLen = 35): string => {
    if (task.length > maxLen) {
      return task.slice(0, maxLen - 3) + '...';
    }
    return task;
  };

  const truncatePath = (path: string, maxLen = 50): string => {
    if (path.length > maxLen) {
      // Try to preserve filename
      const parts = path.split('/');
      if (parts.length > 2) {
        const filename = parts[parts.length - 1];
        const prefix = '~/...';
        const available = maxLen - prefix.length - filename.length - 1;
        if (available > 0) {
          return prefix + '/' + filename;
        }
      }
      return path.slice(0, maxLen - 3) + '...';
    }
    return path;
  };

  return (
    <Box flexDirection="column" marginY={1}>
      {Array.from(typeGroups.entries()).map(([agentType, agents]) => {
        const groupRunning = agents.filter((a) => a.status === 'running').length;
        const allComplete = groupRunning === 0;

        return (
          <Box key={agentType} flexDirection="column">
            {/* Header */}
            <Text>
              <Text color={allComplete ? 'green' : 'yellow'}>{allComplete ? '✓' : '●'} </Text>
              <Text bold dimColor={allComplete}>
                {allComplete ? 'Ran' : 'Running'} {agents.length} {agentType} agent{agents.length > 1 ? 's' : ''}
                {allComplete ? '' : '...'}
              </Text>
              <Text dimColor> (ctrl+o to expand)</Text>
            </Text>

            {/* Agent list */}
            {expanded && agents.map((agent, idx) => {
              const isLast = idx === agents.length - 1;
              const prefix = isLast ? '└─' : '├─';
              const linePrefix = isLast ? '   ' : '│  ';
              const isComplete = agent.status === 'complete';
              const isError = agent.status === 'error';

              return (
                <Box key={agent.id} flexDirection="column">
                  {/* Agent summary line */}
                  <Text dimColor={isComplete}>
                    <Text dimColor>{prefix} </Text>
                    {isComplete && <Text color="green">✓ </Text>}
                    {isError && <Text color="red">✗ </Text>}
                    {!isComplete && !isError && <Text color="yellow">⋯ </Text>}
                    <Text bold={!isComplete}>{truncateTask(agent.task)}</Text>
                    <Text dimColor> · </Text>
                    <Text>{agent.toolCount} tool use{agent.toolCount !== 1 ? 's' : ''}</Text>
                    <Text dimColor> · </Text>
                    <Text>{formatTokens(agent.tokenCount)} tokens</Text>
                  </Text>

                  {/* Current tool activity (only for running agents) */}
                  {agent.currentTool && agent.status === 'running' && (
                    <Text dimColor>
                      {linePrefix}└<Text color="cyan">{truncatePath(agent.currentTool)}</Text>
                    </Text>
                  )}
                </Box>
              );
            })}
          </Box>
        );
      })}
    </Box>
  );
};
