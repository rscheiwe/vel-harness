/**
 * Simple Markdown Renderer for CLI
 */

import React from 'react';
import { Text, Box } from 'ink';

interface MarkdownProps {
  children: string;
}

// Parse inline formatting (bold, code, italic)
const renderInline = (text: string, key: number): React.ReactNode[] => {
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let partKey = 0;

  while (remaining.length > 0) {
    // Bold: **text** or __text__
    const boldMatch = remaining.match(/^(\*\*|__)(.+?)\1/);
    if (boldMatch) {
      parts.push(<Text key={`${key}-${partKey++}`} bold>{boldMatch[2]}</Text>);
      remaining = remaining.slice(boldMatch[0].length);
      continue;
    }

    // Inline code: `code`
    const codeMatch = remaining.match(/^`([^`]+)`/);
    if (codeMatch) {
      parts.push(<Text key={`${key}-${partKey++}`} color="cyan">{codeMatch[1]}</Text>);
      remaining = remaining.slice(codeMatch[0].length);
      continue;
    }

    // Italic: *text* or _text_ (but not ** or __)
    const italicMatch = remaining.match(/^(\*|_)(?!\1)(.+?)\1(?!\1)/);
    if (italicMatch) {
      parts.push(<Text key={`${key}-${partKey++}`} italic>{italicMatch[2]}</Text>);
      remaining = remaining.slice(italicMatch[0].length);
      continue;
    }

    // Plain text until next special character
    const plainMatch = remaining.match(/^[^*_`]+/);
    if (plainMatch) {
      parts.push(<Text key={`${key}-${partKey++}`}>{plainMatch[0]}</Text>);
      remaining = remaining.slice(plainMatch[0].length);
      continue;
    }

    // Single special char that didn't match a pattern
    parts.push(<Text key={`${key}-${partKey++}`}>{remaining[0]}</Text>);
    remaining = remaining.slice(1);
  }

  return parts;
};

export const Markdown: React.FC<MarkdownProps> = ({ children }) => {
  const lines = children.split('\n');

  return (
    <Box flexDirection="column">
      {lines.map((line, i) => {
        // Headers
        const h1Match = line.match(/^# (.+)$/);
        if (h1Match) {
          return (
            <Text key={i} bold color="white">
              {h1Match[1]}
            </Text>
          );
        }

        const h2Match = line.match(/^## (.+)$/);
        if (h2Match) {
          return (
            <Text key={i} bold color="blue">
              {h2Match[1]}
            </Text>
          );
        }

        const h3Match = line.match(/^### (.+)$/);
        if (h3Match) {
          return (
            <Text key={i} bold color="cyan">
              {h3Match[1]}
            </Text>
          );
        }

        // Numbered list
        const numberedMatch = line.match(/^(\d+)\. (.+)$/);
        if (numberedMatch) {
          return (
            <Box key={i}>
              <Text color="yellow">{numberedMatch[1]}. </Text>
              <Text>{renderInline(numberedMatch[2], i)}</Text>
            </Box>
          );
        }

        // Bullet list (-, *, +)
        const bulletMatch = line.match(/^(\s*)([-*+]) (.+)$/);
        if (bulletMatch) {
          const indent = bulletMatch[1].length;
          return (
            <Box key={i} paddingLeft={indent}>
              <Text color="gray">• </Text>
              <Text>{renderInline(bulletMatch[3], i)}</Text>
            </Box>
          );
        }

        // Code block marker (just dim it)
        if (line.startsWith('```')) {
          return <Text key={i} dimColor>{line}</Text>;
        }

        // Empty line
        if (line.trim() === '') {
          return <Text key={i}> </Text>;
        }

        // Regular paragraph with inline formatting
        return <Text key={i}>{renderInline(line, i)}</Text>;
      })}
    </Box>
  );
};
