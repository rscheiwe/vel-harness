# Valis CLI TypeScript Implementation Plan

## Overview

This document outlines the comprehensive plan for building `valis_cli-ts`, a TypeScript CLI application using [Ink](https://github.com/vadimdemedes/ink) (React for CLIs) that leverages the newly built `vel_harness-ts` package.

## Source Analysis: Python valis_cli

### Architecture Summary

The Python valis_cli is built on [Textual](https://textual.textualize.io/) and consists of:

```
valis_cli/
├── app.py              # Main TUI application (ValisCLI)
├── agent.py            # AgentRunner wrapping VelHarness
├── config.py           # Configuration management
├── main.py             # CLI entry point
├── commands/           # Slash command implementations
│   ├── base.py         # Command base class and registry
│   ├── help.py         # /help command
│   ├── reset.py        # /reset command
│   ├── copy.py         # /copy command
│   ├── tokens.py       # /tokens command
│   ├── skills.py       # /skills command
│   ├── permissions.py  # /permissions command
│   ├── config_cmd.py   # /config command
│   └── restart.py      # /restart command
└── widgets/            # UI components
    ├── chat.py         # ChatDisplay, MessageWidget, ToolCallWidget
    ├── input.py        # ChatInput, ChatTextArea
    ├── approval.py     # ApprovalDialog
    └── shimmer.py      # Shimmer animation utilities
```

### Key Features to Port

1. **UI Components**
   - Welcome banner with ASCII art
   - Chat display with message history
   - Streaming text with Markdown rendering
   - Tool call visualization with shimmer animation
   - Status bar with model info, context usage, and spinner
   - Turn envelope showing processing state
   - Input area with multi-line support

2. **Agent Integration**
   - AgentRunner wrapping VelHarness
   - Event streaming (text-delta, tool-call, tool-result, etc.)
   - Tool approval flow
   - Session management

3. **Slash Commands**
   - `/help` - Show available commands
   - `/clear` - Clear chat display
   - `/reset` - Reset session
   - `/copy` - Copy last response to clipboard
   - `/tokens` - Show token usage
   - `/skills` - Manage skills
   - `/permissions` - Manage tool permissions
   - `/config` - View/modify configuration

4. **Configuration**
   - Global config (~/.valis/)
   - Project config (.valis/)
   - settings.local.json for permissions
   - Model settings (provider, model, temperature)

5. **Keyboard Bindings**
   - Ctrl+C: Quit
   - Ctrl+L: Clear
   - Ctrl+R: Reset
   - Escape: Interrupt processing
   - Enter: Submit message
   - Backslash+Enter: Continue to new line

---

## Target: Ink (React for CLIs)

### Ink Overview

Ink is a React-based library for building CLI applications. Key features:

- **React Components**: Box, Text, Newline, Static, Transform
- **Hooks**: useInput, useFocus, useApp, useStdout, useStdin
- **Layout**: Flexbox via Yoga (same as React Native)
- **Third-party**: ink-text-input, ink-spinner, ink-select-input, ink-markdown

### Ink vs Textual Mapping

| Textual | Ink Equivalent |
|---------|----------------|
| App | render() from ink |
| Static | `<Text>` |
| Container | `<Box>` |
| Vertical | `<Box flexDirection="column">` |
| Horizontal | `<Box flexDirection="row">` |
| ScrollableContainer | Custom with useState + viewport |
| TextArea | ink-text-input (enhanced) |
| Button | Custom with useInput |
| ModalScreen | Layer with Box overlay |
| Header | `<Box borderStyle="single">` |
| Footer | `<Box>` at bottom |
| reactive | useState/useReducer |
| message/event | Props/callbacks or context |

---

## Implementation Plan

### Phase 1: Project Setup

#### 1.1 Initialize Project

```bash
mkdir -p /Users/richard.s/vel-harness/valis_cli-ts
cd /Users/richard.s/vel-harness/valis_cli-ts

npm init -y
```

#### 1.2 Dependencies

```json
{
  "dependencies": {
    "ink": "^5.0.1",
    "ink-text-input": "^6.0.0",
    "ink-spinner": "^5.0.0",
    "ink-markdown": "^2.0.0",
    "react": "^18.3.1",
    "vel-harness-ts": "file:../vel_harness-ts",
    "commander": "^12.1.0",
    "chalk": "^5.3.0",
    "clipboardy": "^4.0.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "typescript": "^5.5.0",
    "tsx": "^4.16.0",
    "@types/node": "^20.14.0"
  }
}
```

#### 1.3 TypeScript Configuration

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "jsxImportSource": "react",
    "strict": true,
    "esModuleInterop": true,
    "outDir": "./dist",
    "rootDir": "./src",
    "declaration": true
  }
}
```

### Phase 2: Core Types and Configuration

#### 2.1 Configuration Types (src/config/types.ts)

```typescript
export interface ModelSettings {
  provider: string;
  model: string;
  temperature?: number;
  maxTokens?: number;
}

export interface ApprovalSettings {
  requireApproval: boolean;
  autoApprove: string[];
  alwaysDeny: string[];
}

export interface Permissions {
  allow: string[];
  deny: string[];
  ask: string[];
}

export interface Config {
  globalDir: string;
  projectDir?: string;
  model: ModelSettings;
  approval: ApprovalSettings;
  agentName: string;
  maxTurns: number;
  sandboxEnabled: boolean;
  showThinking: boolean;
  showToolCalls: boolean;
  compactMode: boolean;
}
```

#### 2.2 Configuration Management (src/config/index.ts)

- `detectProjectDir()`: Walk up looking for .valis/
- `getConfig()`: Load config from files
- `saveConfig()`: Persist config changes
- `loadPermissions()`: Load from settings.local.json
- `savePermissions()`: Save to settings.local.json

### Phase 3: Agent Integration

#### 3.1 Event Types (src/agent/events.ts)

```typescript
export enum EventType {
  TEXT_START = 'text-start',
  TEXT_DELTA = 'text-delta',
  TEXT_END = 'text-end',
  TOOL_CALL = 'tool-call',
  TOOL_RESULT = 'tool-result',
  APPROVAL_REQUIRED = 'approval-required',
  ERROR = 'error',
  RESPONSE_METADATA = 'response-metadata',
}

export interface AgentEvent {
  type: EventType;
  data: Record<string, unknown>;
  timestamp: string;
}
```

#### 3.2 Agent Runner (src/agent/runner.ts)

```typescript
export class AgentRunner {
  private harness: VelHarness | null = null;
  private config: Config;
  private sessionId: string;
  private messages: Message[] = [];

  constructor(config: Config);

  async initialize(): Promise<void>;

  async *run(input: string): AsyncGenerator<AgentEvent>;

  checkToolPermission(name: string, args: Record<string, unknown>): 'allow' | 'deny' | 'ask' | null;

  grantPermission(pattern: string, always?: boolean): void;

  resetSession(): void;

  getMessageHistory(): Message[];

  getTokenUsage(): TokenUsage;
}
```

### Phase 4: UI Components

#### 4.1 Component Structure

```
src/components/
├── App.tsx               # Main application component
├── ChatDisplay.tsx       # Message history display
├── ChatInput.tsx         # User input component
├── StatusBar.tsx         # Bottom status bar
├── TurnEnvelope.tsx      # Processing indicator
├── ToolCall.tsx          # Tool call visualization
├── ApprovalDialog.tsx    # Modal for tool approval
├── WelcomeBanner.tsx     # ASCII art welcome
└── Spinner.tsx           # Animated spinner
```

#### 4.2 Main App Component (src/components/App.tsx)

```tsx
import React, { useState, useCallback, useEffect } from 'react';
import { Box, Text, useApp, useInput } from 'ink';
import { WelcomeBanner } from './WelcomeBanner.js';
import { ChatDisplay } from './ChatDisplay.js';
import { ChatInput } from './ChatInput.js';
import { StatusBar } from './StatusBar.js';
import { TurnEnvelope } from './TurnEnvelope.js';
import { ApprovalDialog } from './ApprovalDialog.js';
import { AgentRunner } from '../agent/runner.js';
import { Config } from '../config/types.js';

interface AppProps {
  config: Config;
}

export const App: React.FC<AppProps> = ({ config }) => {
  const { exit } = useApp();
  const [messages, setMessages] = useState<Message[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [pendingApproval, setPendingApproval] = useState<ToolApproval | null>(null);
  const [tokenUsage, setTokenUsage] = useState({ input: 0, output: 0, total: 0 });

  const agent = useMemo(() => new AgentRunner(config), [config]);

  useInput((input, key) => {
    if (key.ctrl && input === 'c') exit();
    if (key.escape && isProcessing) handleInterrupt();
  });

  const handleSubmit = useCallback(async (input: string) => {
    if (input.startsWith('/')) {
      await handleSlashCommand(input);
      return;
    }

    setIsProcessing(true);
    addMessage({ role: 'user', content: input });

    try {
      for await (const event of agent.run(input)) {
        handleAgentEvent(event);
      }
    } catch (error) {
      addMessage({ role: 'error', content: String(error) });
    } finally {
      setIsProcessing(false);
    }
  }, [agent]);

  return (
    <Box flexDirection="column" height="100%">
      <WelcomeBanner model={config.model.model} cwd={process.cwd()} />
      <ChatDisplay messages={messages} streamingText={streamingText} />
      <TurnEnvelope active={isProcessing} tokens={tokenUsage} />
      <ChatInput onSubmit={handleSubmit} disabled={isProcessing} />
      <StatusBar
        model={config.model.model}
        isProcessing={isProcessing}
        tokens={tokenUsage}
      />
      {pendingApproval && (
        <ApprovalDialog
          tool={pendingApproval}
          onApprove={() => handleApprovalResponse(true)}
          onDeny={() => handleApprovalResponse(false)}
          onAlways={() => handleApprovalResponse(true, true)}
        />
      )}
    </Box>
  );
};
```

#### 4.3 Chat Display (src/components/ChatDisplay.tsx)

```tsx
import React, { useMemo } from 'react';
import { Box, Text, Static } from 'ink';
import { Markdown } from './Markdown.js';
import { ToolCallWidget } from './ToolCall.js';

interface Message {
  role: 'user' | 'assistant' | 'system' | 'error';
  content: string;
  timestamp?: Date;
}

interface ChatDisplayProps {
  messages: Message[];
  streamingText?: string;
  toolCalls?: ToolCall[];
}

export const ChatDisplay: React.FC<ChatDisplayProps> = ({
  messages,
  streamingText,
  toolCalls,
}) => {
  return (
    <Box flexDirection="column" flexGrow={1} overflow="hidden">
      {/* Static preserves previous content efficiently */}
      <Static items={messages}>
        {(message, index) => (
          <MessageWidget key={index} message={message} />
        )}
      </Static>

      {/* Active tool calls with shimmer */}
      {toolCalls?.filter(tc => tc.pending).map(tc => (
        <ToolCallWidget key={tc.id} toolCall={tc} />
      ))}

      {/* Streaming text */}
      {streamingText && (
        <Box paddingX={1}>
          <Markdown>{streamingText}</Markdown>
        </Box>
      )}
    </Box>
  );
};

const MessageWidget: React.FC<{ message: Message }> = ({ message }) => {
  const styles = {
    user: { borderColor: 'blue', prefix: 'You: ' },
    assistant: { borderColor: 'green', prefix: '' },
    system: { borderColor: 'yellow', prefix: '' },
    error: { borderColor: 'red', prefix: 'Error: ' },
  };

  const style = styles[message.role];

  return (
    <Box
      flexDirection="column"
      borderStyle="single"
      borderColor={style.borderColor}
      paddingX={1}
      marginY={message.role === 'user' ? 1 : 0}
    >
      {message.role === 'assistant' ? (
        <Markdown>{message.content}</Markdown>
      ) : (
        <Text color={message.role === 'error' ? 'red' : undefined}>
          {style.prefix}{message.content}
        </Text>
      )}
    </Box>
  );
};
```

#### 4.4 Chat Input (src/components/ChatInput.tsx)

```tsx
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
    if (!value.trim() || disabled) return;

    // Add to history
    setHistory(prev => [...prev, value]);
    setHistoryIndex(-1);

    onSubmit(value);
    setValue('');
  }, [value, disabled, onSubmit]);

  useInput((input, key) => {
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
  });

  return (
    <Box borderStyle="round" borderColor={disabled ? 'gray' : 'cyan'} paddingX={1}>
      <Text color="cyan">&gt; </Text>
      <TextInput
        value={value}
        onChange={setValue}
        placeholder={placeholder}
        showCursor={!disabled}
      />
    </Box>
  );
};
```

#### 4.5 Status Bar (src/components/StatusBar.tsx)

```tsx
import React from 'react';
import { Box, Text } from 'ink';
import Spinner from 'ink-spinner';

interface StatusBarProps {
  model: string;
  isProcessing: boolean;
  tokens: { input: number; output: number; total: number };
  contextPercent?: number;
  elapsedSeconds?: number;
}

export const StatusBar: React.FC<StatusBarProps> = ({
  model,
  isProcessing,
  tokens,
  contextPercent = 0,
  elapsedSeconds = 0,
}) => {
  const formatTokens = (n: number) => n >= 1000 ? `${(n/1000).toFixed(1)}k` : String(n);
  const formatDuration = (s: number) => {
    if (s < 60) return `${Math.floor(s)}s`;
    return `${Math.floor(s/60)}m ${Math.floor(s%60)}s`;
  };

  const contextColor = contextPercent >= 95 ? 'red'
    : contextPercent >= 85 ? 'yellow'
    : contextPercent >= 70 ? 'cyan'
    : 'green';

  return (
    <Box paddingX={2} backgroundColor="gray">
      {isProcessing ? (
        <>
          <Spinner type="dots" />
          <Text> Processing (esc to interrupt · {formatDuration(elapsedSeconds)})</Text>
        </>
      ) : (
        <>
          <Text>⚡ {model}</Text>
          <Text>  </Text>
          <Text color={contextColor}>
            {formatTokens(tokens.total)}/{formatTokens(200000)} ({contextPercent.toFixed(0)}%)
          </Text>
          <Text>  </Text>
          <Text dimColor>ctrl+c: quit | /help: commands</Text>
        </>
      )}
    </Box>
  );
};
```

#### 4.6 Tool Call Widget (src/components/ToolCall.tsx)

```tsx
import React, { useState, useEffect } from 'react';
import { Box, Text } from 'ink';

interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
  pending: boolean;
  result?: unknown;
}

const SHIMMER_CHARS = ['·', '∴', '·', '∵', '·', '⁖', '·', '∷'];

export const ToolCallWidget: React.FC<{ toolCall: ToolCall }> = ({ toolCall }) => {
  const [shimmerIndex, setShimmerIndex] = useState(0);

  useEffect(() => {
    if (!toolCall.pending) return;

    const interval = setInterval(() => {
      setShimmerIndex(i => (i + 1) % SHIMMER_CHARS.length);
    }, 150);

    return () => clearInterval(interval);
  }, [toolCall.pending]);

  const formatArgs = () => {
    return Object.entries(toolCall.args)
      .map(([k, v]) => {
        const str = String(v);
        return `${k}=${str.length > 50 ? str.slice(0, 47) + '...' : str}`;
      })
      .join(', ');
  };

  const formatResult = () => {
    if (!toolCall.result) return 'Done';
    if (typeof toolCall.result === 'object') {
      const r = toolCall.result as Record<string, unknown>;
      if (r.error) return `Error: ${String(r.error).slice(0, 40)}`;
      if (r.count) return `Found ${r.count} items`;
      if (r.lines) return `${r.lines} lines`;
    }
    return 'Done';
  };

  if (toolCall.pending) {
    return (
      <Box paddingX={1}>
        <Text color="cyan">
          {SHIMMER_CHARS[shimmerIndex]} Running {toolCall.name}...
        </Text>
      </Box>
    );
  }

  return (
    <Box paddingX={1} flexDirection="column">
      <Text>
        <Text color="green">● </Text>
        <Text color="cyan" dimColor>{toolCall.name}({formatArgs()})</Text>
      </Text>
      <Text dimColor>  └ {formatResult()}</Text>
    </Box>
  );
};
```

#### 4.7 Approval Dialog (src/components/ApprovalDialog.tsx)

```tsx
import React from 'react';
import { Box, Text, useInput } from 'ink';

interface ApprovalDialogProps {
  tool: {
    id: string;
    name: string;
    args: Record<string, unknown>;
  };
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
      padding={1}
      marginY={1}
    >
      <Text bold color="yellow">Tool Approval Required</Text>
      <Box marginY={1}>
        <Text>Tool: </Text>
        <Text bold color="cyan">{tool.name}</Text>
      </Box>

      <Box flexDirection="column" backgroundColor="blackBright" padding={1}>
        <Text>Arguments:</Text>
        {Object.entries(tool.args).map(([key, value]) => (
          <Text key={key} dimColor>  {key}: {JSON.stringify(value)}</Text>
        ))}
      </Box>

      <Box marginTop={1} justifyContent="space-around">
        <Text>[y] Approve  </Text>
        <Text>[a] Always Allow  </Text>
        <Text>[n] Deny</Text>
      </Box>
    </Box>
  );
};
```

#### 4.8 Welcome Banner (src/components/WelcomeBanner.tsx)

```tsx
import React from 'react';
import { Box, Text } from 'ink';

const ASCII_ART = `
██╗   ██╗ █████╗ ██╗     ██╗███████╗
██║   ██║██╔══██╗██║     ██║██╔════╝
██║   ██║███████║██║     ██║███████╗
╚██╗ ██╔╝██╔══██║██║     ██║╚════██║
 ╚████╔╝ ██║  ██║███████╗██║███████║
  ╚═══╝  ╚═╝  ╚═╝╚══════╝╚═╝╚══════╝
`.trim();

interface WelcomeBannerProps {
  model: string;
  cwd: string;
}

export const WelcomeBanner: React.FC<WelcomeBannerProps> = ({ model, cwd }) => {
  // Shorten cwd with ~ for home
  const home = process.env.HOME || '';
  const displayCwd = cwd.startsWith(home) ? '~' + cwd.slice(home.length) : cwd;

  return (
    <Box
      flexDirection="column"
      alignItems="center"
      borderStyle="round"
      borderColor="cyan"
      padding={1}
      marginY={1}
    >
      <Text color="cyan" bold>{ASCII_ART}</Text>
      <Box marginTop={1} flexDirection="column" alignItems="center">
        <Text bold>{model}</Text>
        <Text dimColor>{displayCwd}</Text>
        <Text dimColor>Type a message to chat, or /help for commands</Text>
      </Box>
    </Box>
  );
};
```

### Phase 5: Slash Commands

#### 5.1 Command System (src/commands/index.ts)

```typescript
export interface CommandResult {
  success: boolean;
  message?: string;
  data?: Record<string, unknown>;
  shouldExit?: boolean;
}

export interface CommandContext {
  agent: AgentRunner;
  config: Config;
  clearMessages: () => void;
  addMessage: (msg: Message) => void;
}

export interface Command {
  name: string;
  description: string;
  aliases?: string[];
  execute(args: string[], context: CommandContext): Promise<CommandResult>;
}

export const commands: Command[] = [
  helpCommand,
  clearCommand,
  resetCommand,
  copyCommand,
  tokensCommand,
  skillsCommand,
  permissionsCommand,
  configCommand,
];

export function getCommand(name: string): Command | undefined {
  return commands.find(c => c.name === name || c.aliases?.includes(name));
}
```

#### 5.2 Individual Commands

```typescript
// src/commands/help.ts
export const helpCommand: Command = {
  name: 'help',
  description: 'Show available commands',
  aliases: ['h', '?'],
  async execute(args, context) {
    const helpText = commands
      .map(c => `  /${c.name.padEnd(12)} - ${c.description}`)
      .join('\n');
    return {
      success: true,
      message: `Available Commands:\n\n${helpText}`,
    };
  },
};

// src/commands/clear.ts
export const clearCommand: Command = {
  name: 'clear',
  description: 'Clear chat display',
  async execute(args, context) {
    context.clearMessages();
    return { success: true, message: 'Chat cleared' };
  },
};

// src/commands/reset.ts
export const resetCommand: Command = {
  name: 'reset',
  description: 'Reset session',
  async execute(args, context) {
    context.agent.resetSession();
    context.clearMessages();
    return { success: true, message: 'Session reset. Starting fresh conversation.' };
  },
};

// src/commands/copy.ts
export const copyCommand: Command = {
  name: 'copy',
  description: 'Copy last response to clipboard',
  async execute(args, context) {
    const lastMessage = context.agent.getLastAssistantMessage();
    if (!lastMessage) {
      return { success: false, message: 'No assistant message to copy' };
    }
    await clipboard.write(lastMessage);
    return { success: true, message: 'Copied to clipboard' };
  },
};

// src/commands/tokens.ts
export const tokensCommand: Command = {
  name: 'tokens',
  description: 'Show token usage',
  async execute(args, context) {
    const usage = context.agent.getTokenUsage();
    return {
      success: true,
      message: `Token Usage:
  Input:  ${usage.input.toLocaleString()}
  Output: ${usage.output.toLocaleString()}
  Total:  ${usage.total.toLocaleString()}
  Cache:  ${usage.cacheRead.toLocaleString()} read, ${usage.cacheCreation.toLocaleString()} created`,
    };
  },
};
```

### Phase 6: CLI Entry Point

#### 6.1 Main Entry (src/cli.tsx)

```tsx
#!/usr/bin/env node

import React from 'react';
import { render } from 'ink';
import { Command } from 'commander';
import { App } from './components/App.js';
import { getConfig } from './config/index.js';

const program = new Command();

program
  .name('valis')
  .description('Valis CLI - AI agent assistant')
  .version('1.0.0')
  .option('-m, --model <model>', 'Model to use')
  .option('-p, --provider <provider>', 'Provider (anthropic, openai)')
  .option('--no-sandbox', 'Disable sandbox mode')
  .option('--compact', 'Compact mode')
  .action(async (options) => {
    const config = getConfig();

    if (options.model) {
      config.model.model = options.model;
    }
    if (options.provider) {
      config.model.provider = options.provider;
    }
    if (options.sandbox === false) {
      config.sandboxEnabled = false;
    }
    if (options.compact) {
      config.compactMode = true;
    }

    render(<App config={config} />);
  });

program.parse();
```

### Phase 7: Testing Strategy

#### 7.1 Unit Tests
- Configuration loading/saving
- Permission pattern matching
- Command parsing
- Event normalization

#### 7.2 Component Tests
- Use ink-testing-library for component tests
- Test each component in isolation

```typescript
import { render } from 'ink-testing-library';
import { StatusBar } from '../src/components/StatusBar.js';

test('StatusBar shows processing state', () => {
  const { lastFrame } = render(
    <StatusBar model="claude-3-opus" isProcessing={true} tokens={{ total: 1500 }} />
  );
  expect(lastFrame()).toContain('Processing');
});
```

#### 7.3 Integration Tests
- Full CLI flow with mock agent
- Slash command execution
- Tool approval flow

---

## File Structure

```
valis_cli-ts/
├── package.json
├── tsconfig.json
├── src/
│   ├── cli.tsx                   # Entry point
│   ├── config/
│   │   ├── index.ts              # Config management
│   │   └── types.ts              # Config types
│   ├── agent/
│   │   ├── runner.ts             # AgentRunner
│   │   ├── events.ts             # Event types
│   │   └── approval.ts           # Approval handler
│   ├── components/
│   │   ├── App.tsx               # Main app
│   │   ├── ChatDisplay.tsx       # Chat history
│   │   ├── ChatInput.tsx         # Input field
│   │   ├── StatusBar.tsx         # Status bar
│   │   ├── TurnEnvelope.tsx      # Processing indicator
│   │   ├── ToolCall.tsx          # Tool visualization
│   │   ├── ApprovalDialog.tsx    # Approval modal
│   │   ├── WelcomeBanner.tsx     # Welcome screen
│   │   ├── Spinner.tsx           # Spinner component
│   │   └── Markdown.tsx          # Markdown renderer
│   ├── commands/
│   │   ├── index.ts              # Command registry
│   │   ├── help.ts
│   │   ├── clear.ts
│   │   ├── reset.ts
│   │   ├── copy.ts
│   │   ├── tokens.ts
│   │   ├── skills.ts
│   │   └── permissions.ts
│   └── utils/
│       ├── clipboard.ts          # Clipboard utils
│       └── format.ts             # Formatting utils
├── test/
│   ├── components/
│   ├── commands/
│   └── integration/
└── dist/                         # Build output
```

---

## Implementation Timeline

### Week 1: Foundation
- [ ] Project setup and dependencies
- [ ] Configuration system
- [ ] Basic App shell with Box layout
- [ ] WelcomeBanner component
- [ ] StatusBar component

### Week 2: Core UI
- [ ] ChatDisplay with Static
- [ ] ChatInput with history
- [ ] Basic message rendering
- [ ] Streaming text display

### Week 3: Agent Integration
- [ ] AgentRunner wrapper for vel_harness-ts
- [ ] Event streaming and handling
- [ ] Tool call visualization
- [ ] Token tracking

### Week 4: Features
- [ ] Slash command system
- [ ] All slash commands implemented
- [ ] ApprovalDialog component
- [ ] Permission system

### Week 5: Polish
- [ ] Shimmer animations
- [ ] Markdown rendering
- [ ] Error handling
- [ ] Testing

---

## Key Differences from Python Version

1. **React Paradigm**: State management via hooks instead of reactive attributes
2. **No CSS**: Styling via props (borderStyle, backgroundColor, etc.)
3. **Static Component**: Ink's Static preserves chat history efficiently
4. **Event Handling**: useInput hook instead of binding system
5. **No ModalScreen**: Overlay pattern with Box layering
6. **Simpler Layout**: Flexbox only (no dock, no complex positioning)

## Dependencies on vel_harness-ts

```typescript
// Required exports from vel_harness-ts
import { VelHarness, createHarness } from 'vel-harness-ts';
import type {
  HarnessConfig,
  RunOptions,
  StreamEvent
} from 'vel-harness-ts';
```

The AgentRunner will:
1. Create VelHarness instance with config
2. Call `harness.runStream()` for user messages
3. Normalize StreamEvents to AgentEvents for UI consumption
4. Track message history and token usage

---

## Risk Mitigation

1. **ink-markdown Quality**: May need custom Markdown component using marked + chalk
2. **Input Limitations**: ink-text-input is basic; may need custom for multi-line
3. **Scrolling**: Ink has limited scroll support; may need custom viewport
4. **Image Support**: Unlike Python version, defer image paste support to later

## Success Criteria

1. All slash commands work as expected
2. Streaming text displays smoothly
3. Tool calls show with shimmer animation
4. Token usage tracked and displayed
5. Approval flow functional
6. Configuration persists correctly
7. Session reset works properly
