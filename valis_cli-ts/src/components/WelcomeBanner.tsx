/**
 * Welcome Banner Component
 */

import React from 'react';
import { Box, Text } from 'ink';
import * as os from 'os';

const ASCII_ART = [
  '██╗   ██╗ █████╗ ██╗     ██╗███████╗',
  '██║   ██║██╔══██╗██║     ██║██╔════╝',
  '██║   ██║███████║██║     ██║███████╗',
  '╚██╗ ██╔╝██╔══██║██║     ██║╚════██║',
  ' ╚████╔╝ ██║  ██║███████╗██║███████║',
  '  ╚═══╝  ╚═╝  ╚═╝╚══════╝╚═╝╚══════╝',
];

interface WelcomeBannerProps {
  model: string;
  cwd: string;
}

export const WelcomeBanner: React.FC<WelcomeBannerProps> = ({ model, cwd }) => {
  // Shorten cwd with ~ for home
  const home = os.homedir();
  const displayCwd = cwd.startsWith(home) ? '~' + cwd.slice(home.length) : cwd;

  return (
    <Box
      flexDirection="column"
      alignItems="center"
      borderStyle="round"
      borderColor="cyan"
      paddingX={2}
      paddingY={1}
      marginBottom={1}
    >
      {ASCII_ART.map((line, i) => (
        <Text key={i} color="cyan" bold>
          {line}
        </Text>
      ))}
      <Box marginTop={1} flexDirection="column" alignItems="center">
        <Text bold>{model}</Text>
        <Text dimColor>{displayCwd}</Text>
        <Text dimColor>Type a message to chat, or /help for commands</Text>
      </Box>
    </Box>
  );
};
