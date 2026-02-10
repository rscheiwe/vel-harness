/**
 * Rolling Activity Window
 *
 * Shows recent tool activity in a fixed-height window.
 * Older activity rolls off, counter tracks hidden items.
 */

import React from 'react';
import { Box, Text } from 'ink';

interface ActivityItem {
  id: string;
  description: string;
  status: 'pending' | 'complete' | 'error';
  timestamp: number;
}

interface ActivityWindowProps {
  /** Agent/task header */
  header: string;
  /** Activity items (most recent last) */
  items: ActivityItem[];
  /** Max visible slots (default: 3) */
  visibleSlots?: number;
  /** Max width for truncation */
  maxWidth?: number;
}

export const ActivityWindow: React.FC<ActivityWindowProps> = ({
  header,
  items,
  visibleSlots = 3,
  maxWidth = 60,
}) => {
  // Get visible items (most recent)
  const hiddenCount = Math.max(0, items.length - visibleSlots);
  const visibleItems = items.slice(-visibleSlots);

  const truncate = (text: string): string => {
    if (text.length > maxWidth) {
      return text.slice(0, maxWidth - 1) + '…';
    }
    return text;
  };

  const getStatusIcon = (status: ActivityItem['status']): string => {
    switch (status) {
      case 'pending':
        return '⋯';
      case 'complete':
        return '✓';
      case 'error':
        return '✗';
    }
  };

  const getStatusColor = (status: ActivityItem['status']): string => {
    switch (status) {
      case 'pending':
        return 'yellow';
      case 'complete':
        return 'green';
      case 'error':
        return 'red';
    }
  };

  if (items.length === 0) {
    return null;
  }

  return (
    <Box flexDirection="column" borderStyle="round" borderColor="gray" paddingX={1}>
      {/* Header */}
      <Text>
        <Text color="cyan">● </Text>
        <Text bold>{header}</Text>
      </Text>

      {/* Activity slots */}
      {visibleItems.map((item, index) => {
        const isLast = index === visibleItems.length - 1;
        const prefix = isLast ? '└─' : '├─';
        const status = item.status;

        return (
          <Text key={item.id} dimColor={status === 'complete'}>
            {'  '}
            <Text dimColor>{prefix}</Text>
            {' '}
            <Text color={getStatusColor(status)}>{getStatusIcon(status)}</Text>
            {' '}
            <Text>{truncate(item.description)}</Text>
          </Text>
        );
      })}

      {/* Hidden counter */}
      {hiddenCount > 0 && (
        <Text dimColor>
          {'  '}+{hiddenCount} more tool uses
        </Text>
      )}
    </Box>
  );
};
