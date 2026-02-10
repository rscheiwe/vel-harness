/**
 * Status Bar Component
 */

import React from 'react';
import { Box, Text } from 'ink';
import type { TokenUsage } from '../config/types.js';

interface StatusBarProps {
  model: string;
  tokens: TokenUsage;
  contextMax?: number;
}

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

export const StatusBar: React.FC<StatusBarProps> = ({
  model,
  tokens,
  contextMax = 200000,
}) => {
  const contextPercent = contextMax > 0 ? (tokens.total / contextMax) * 100 : 0;

  const contextColor =
    contextPercent >= 95
      ? 'red'
      : contextPercent >= 85
        ? 'yellow'
        : contextPercent >= 70
          ? 'cyan'
          : 'green';

  // Always show model info (processing state is shown in TurnEnvelope)
  return (
    <Box paddingX={2} justifyContent="space-between">
      <Box>
        <Text>⚡ {model}</Text>
        <Text>  </Text>
        <Text color={contextColor}>
          {formatTokens(tokens.total)}/{formatTokens(contextMax)} (
          {contextPercent.toFixed(0)}%)
        </Text>
      </Box>
      <Text dimColor>ctrl+c: quit | /help: commands</Text>
    </Box>
  );
};
