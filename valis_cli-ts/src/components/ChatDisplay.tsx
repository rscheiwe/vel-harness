/**
 * Chat Display Component
 *
 * Uses <Static> for completed items (scrolls naturally) and
 * dynamic rendering for active items (streaming text, pending tools).
 */

import React from 'react';
import { Box, Text } from 'ink';
import type { ChatItem } from '../config/types.js';
import { ToolCallWidget } from './ToolCall.js';
import { Spinner } from './Spinner.js';
import { Markdown } from './Markdown.js';

interface ChatDisplayProps {
  items: ChatItem[];
  isLoading?: boolean;
}

// Render a single chat item
const ChatItemWidget: React.FC<{ item: ChatItem }> = ({ item }) => {
  switch (item.kind) {
    case 'user':
      // Blue background for user messages
      return (
        <Box marginY={1}>
          <Text backgroundColor="blue" color="white"> You: {item.content} </Text>
        </Box>
      );

    case 'assistant-text':
      // Blue left border for assistant messages
      return (
        <Box marginY={1} flexDirection="row">
          <Box width={3} flexShrink={0}>
            <Text color="blue"> │</Text>
          </Box>
          <Box flexGrow={1} flexShrink={1} flexDirection="column">
            <Markdown>{item.content}</Markdown>
          </Box>
        </Box>
      );

    case 'tool':
      return (
        <Box marginLeft={2}>
          <ToolCallWidget toolCall={item.toolCall} />
        </Box>
      );

    case 'system':
      // Yellow left border for system messages
      return (
        <Box flexDirection="row">
          <Box width={3} flexShrink={0}>
            <Text color="yellow"> │</Text>
          </Box>
          <Box flexGrow={1} flexShrink={1}>
            <Text wrap="wrap" dimColor>{item.content}</Text>
          </Box>
        </Box>
      );

    case 'error':
      // Red left border for errors
      return (
        <Box flexDirection="row">
          <Box width={3} flexShrink={0}>
            <Text color="red"> │</Text>
          </Box>
          <Box flexGrow={1} flexShrink={1}>
            <Text color="red" wrap="wrap">Error: {item.content}</Text>
          </Box>
        </Box>
      );

    default:
      return null;
  }
};

// Generate a unique key for a chat item
const getItemKey = (item: ChatItem, index: number): string => {
  if (item.kind === 'tool') return `tool-${item.toolCall.id}`;
  return `${item.kind}-${index}`;
};

export const ChatDisplay: React.FC<ChatDisplayProps> = ({
  items,
  isLoading,
}) => {
  return (
    <Box flexDirection="column">
      {items.map((item, index) => (
        <ChatItemWidget
          key={getItemKey(item, index)}
          item={item}
        />
      ))}

      {isLoading && (
        <Box paddingX={1}>
          <Spinner />
          <Text> Agent is thinking...</Text>
        </Box>
      )}
    </Box>
  );
};
