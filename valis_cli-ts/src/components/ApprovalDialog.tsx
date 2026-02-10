/**
 * Approval Dialog Component
 */

import React from 'react';
import { Box, Text, useInput } from 'ink';
import type { ToolApproval } from '../config/types.js';

interface ApprovalDialogProps {
  tool: ToolApproval;
  onApprove: () => void;
  onDeny: () => void;
  onAlways: () => void;
}

export const ApprovalDialog: React.FC<ApprovalDialogProps> = ({
  tool,
  onApprove,
  onDeny,
  onAlways,
}) => {
  useInput((input, key) => {
    if (input === 'y' || key.return) onApprove();
    else if (input === 'n' || key.escape) onDeny();
    else if (input === 'a') onAlways();
  });

  return (
    <Box
      flexDirection="column"
      borderStyle="double"
      borderColor="yellow"
      paddingX={2}
      paddingY={1}
      marginY={1}
    >
      <Text bold color="yellow">
        Tool Approval Required
      </Text>

      <Box marginY={1}>
        <Text>Tool: </Text>
        <Text bold color="cyan">
          {tool.name}
        </Text>
      </Box>

      <Box flexDirection="column" paddingX={1} paddingY={1}>
        <Text>Arguments:</Text>
        {(() => {
          // Handle both string and object args
          const rawArgs = tool.args;

          // Parse string args
          const parseArgs = (): Record<string, unknown> | null => {
            if (typeof rawArgs === 'string') {
              try {
                return JSON.parse(rawArgs) as Record<string, unknown>;
              } catch {
                return null; // Parse failed
              }
            }
            if (rawArgs && typeof rawArgs === 'object') {
              return rawArgs as Record<string, unknown>;
            }
            return null;
          };

          const args = parseArgs();

          // If couldn't parse, show raw string
          if (!args) {
            const str = String(rawArgs);
            const display = str.length > 100 ? str.slice(0, 97) + '...' : str;
            return <Text dimColor>{'  '}{display}</Text>;
          }

          return Object.entries(args).map(([key, value]) => {
            const valueStr = typeof value === 'string' ? value : JSON.stringify(value);
            const display = valueStr.length > 60 ? valueStr.slice(0, 57) + '...' : valueStr;
            return (
              <Text key={key} dimColor>
                {'  '}{key}: {display}
              </Text>
            );
          });
        })()}
      </Box>

      <Box marginTop={1} justifyContent="center">
        <Text>[y] Approve  </Text>
        <Text>[a] Always Allow  </Text>
        <Text>[n] Deny</Text>
      </Box>

      <Box marginTop={1}>
        <Text dimColor>Permission saved to .valis/settings.local.json</Text>
      </Box>
    </Box>
  );
};
