/**
 * Chat Input Component
 */

import React, { useState, useCallback } from 'react';
import { Box, Text, useInput } from 'ink';
import TextInput from 'ink-text-input';

interface ChatInputProps {
  onSubmit: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export const ChatInput: React.FC<ChatInputProps> = ({
  onSubmit,
  disabled = false,
  placeholder = 'Enter message...',
}) => {
  const [value, setValue] = useState('');
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;

    // Add to history
    setHistory((prev) => [...prev, trimmed]);
    setHistoryIndex(-1);

    onSubmit(trimmed);
    setValue('');
  }, [value, disabled, onSubmit]);

  useInput(
    (input, key) => {
      if (disabled) return;

      // Submit on Enter
      if (key.return) {
        handleSubmit();
        return;
      }

      // History navigation
      if (key.upArrow && history.length > 0) {
        const newIndex = Math.min(historyIndex + 1, history.length - 1);
        setHistoryIndex(newIndex);
        setValue(history[history.length - 1 - newIndex]);
      }
      if (key.downArrow && historyIndex > 0) {
        const newIndex = historyIndex - 1;
        setHistoryIndex(newIndex);
        setValue(history[history.length - 1 - newIndex]);
      }
      if (key.downArrow && historyIndex === 0) {
        setHistoryIndex(-1);
        setValue('');
      }
    },
    { isActive: !disabled }
  );

  return (
    <Box
      borderStyle="round"
      borderColor={disabled ? 'gray' : 'cyan'}
      paddingX={1}
    >
      <Text color="cyan">&gt; </Text>
      <TextInput
        value={value}
        onChange={setValue}
        placeholder={disabled ? 'Processing...' : placeholder}
        showCursor={!disabled}
        focus={!disabled}
      />
    </Box>
  );
};
