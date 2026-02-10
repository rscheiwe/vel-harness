/**
 * Turn Envelope Component
 *
 * Shows processing state with shimmer animation.
 */

import React, { useState, useEffect } from 'react';
import { Box, Text } from 'ink';
import type { TokenUsage } from '../config/types.js';

interface TurnEnvelopeProps {
  active: boolean;
  tokens: TokenUsage;
  verb?: string;
}

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

// Simple pulsing indicator (no animation to reduce re-renders)
const PulsingText: React.FC<{ text: string }> = ({ text }) => {
  return <Text color="cyan">{text}...</Text>;
};

export const TurnEnvelope: React.FC<TurnEnvelopeProps> = ({
  active,
  tokens,
  verb = 'Harnessing',
}) => {
  const [elapsed, setElapsed] = useState(0);

  // Elapsed time counter (every second)
  useEffect(() => {
    if (!active) {
      setElapsed(0);
      return;
    }

    const timer = setInterval(() => {
      setElapsed((e) => e + 1);
    }, 1000);

    return () => clearInterval(timer);
  }, [active]);

  if (!active) {
    // Return empty spacer to prevent layout jump
    return <Box paddingX={1}><Text> </Text></Box>;
  }

  return (
    <Box paddingX={1}>
      <PulsingText text={verb} />
      <Text dimColor>
        {' '}
        (esc to interrupt · {elapsed}s · ↓ {formatTokens(tokens.total)} tokens)
      </Text>
    </Box>
  );
};
