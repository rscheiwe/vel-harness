/**
 * Main App Component
 */

import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { Box, useApp, useInput } from 'ink';
import { WelcomeBanner } from './WelcomeBanner.js';
import { ChatDisplay } from './ChatDisplay.js';
import { ChatInput } from './ChatInput.js';
import { StatusBar } from './StatusBar.js';
import { TurnEnvelope } from './TurnEnvelope.js';
import { ApprovalDialog } from './ApprovalDialog.js';
import { SubagentPanel, SubagentInfo } from './SubagentPanel.js';
import { AgentRunner, EventType } from '../agent/index.js';
import { executeCommand, getCommand } from '../commands/index.js';
import type { Config, Message, ToolCall, ToolApproval, TokenUsage, ChatItem } from '../config/types.js';

/** Subagent tracking - uses SubagentInfo from SubagentPanel */

interface AppProps {
  config: Config;
}

export const App: React.FC<AppProps> = ({ config }) => {
  const { exit } = useApp();

  // State - unified chat history
  const [chatItems, setChatItems] = useState<ChatItem[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [pendingApproval, setPendingApproval] = useState<ToolApproval | null>(null);
  const [tokenUsage, setTokenUsage] = useState<TokenUsage>({
    input: 0,
    output: 0,
    total: 0,
    cacheRead: 0,
    cacheCreation: 0,
  });
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [showWelcome, setShowWelcome] = useState(true);
  const [activeSubagents, setActiveSubagents] = useState<Map<string, SubagentInfo>>(new Map());

  // Agent
  const agent = useMemo(() => new AgentRunner(config), [config]);

  // Timer ref for elapsed time
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Handle keyboard input
  useInput((input, key) => {
    if (key.ctrl && input === 'c') {
      exit();
    }
    if (key.escape && isProcessing) {
      // TODO: Implement interrupt
    }
  });

  // Elapsed time tracking
  useEffect(() => {
    if (isProcessing) {
      setElapsedSeconds(0);
      timerRef.current = setInterval(() => {
        setElapsedSeconds((e) => e + 1);
      }, 1000);
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [isProcessing]);

  // Add chat item helper
  const addChatItem = useCallback((item: ChatItem) => {
    setChatItems((prev) => [...prev, item]);
  }, []);

  // Clear chat helper
  const clearChat = useCallback(() => {
    setChatItems([]);
    setShowWelcome(false);
  }, []);

  // Handle slash commands
  const handleSlashCommand = useCallback(
    async (input: string) => {
      const parts = input.slice(1).split(/\s+/);
      const cmdName = parts[0].toLowerCase();
      const args = parts.slice(1);

      const cmd = getCommand(cmdName);
      if (!cmd) {
        addChatItem({
          kind: 'error',
          content: `Unknown command: /${cmdName}`,
          timestamp: new Date(),
        });
        return;
      }

      // Adapter for old command interface
      const addMessage = (msg: Message) => {
        if (msg.role === 'system') {
          addChatItem({ kind: 'system', content: msg.content, timestamp: msg.timestamp });
        } else if (msg.role === 'error') {
          addChatItem({ kind: 'error', content: msg.content, timestamp: msg.timestamp });
        }
      };

      const result = await executeCommand(cmd, args, {
        agent,
        config,
        addMessage,
        clearMessages: clearChat,
      });

      if (result.message) {
        addChatItem({
          kind: 'system',
          content: result.message,
          timestamp: new Date(),
        });
      }

      if (result.shouldExit) {
        exit();
      }
    },
    [agent, config, addChatItem, clearChat, exit]
  );

  // Handle approval response
  const handleApprovalResponse = useCallback(
    (approved: boolean, always = false) => {
      if (!pendingApproval) return;

      if (approved && always) {
        agent.grantPermission(pendingApproval.name, true);
      } else if (!approved && always) {
        agent.denyPermission(pendingApproval.name, true);
      }

      // Signal the agent to continue (pass tool name for timing coordination)
      agent.respondToApproval(approved, pendingApproval.name);
      setPendingApproval(null);
    },
    [pendingApproval, agent]
  );

  // Handle message submission
  const handleSubmit = useCallback(
    async (input: string) => {
      // Hide welcome on first message
      if (showWelcome) {
        setShowWelcome(false);
      }

      // Handle slash commands
      if (input.startsWith('/')) {
        await handleSlashCommand(input);
        return;
      }

      setIsProcessing(true);

      // Clear active subagents from previous turn
      setActiveSubagents(new Map());

      // Snapshot where this turn starts in chatItems
      const turnStartIndex = chatItems.length;

      // Track this turn's items locally
      let turnItems: ChatItem[] = [];
      let currentTextContent = '';
      let updatePending = false;
      let lastUpdateTime = 0;
      const UPDATE_THROTTLE_MS = 50; // Throttle updates to reduce re-renders

      // Helper to update chatItems with current turn's items (throttled)
      const updateChat = (force = false) => {
        const now = Date.now();
        if (!force && now - lastUpdateTime < UPDATE_THROTTLE_MS) {
          // Schedule a pending update
          if (!updatePending) {
            updatePending = true;
            setTimeout(() => {
              updatePending = false;
              lastUpdateTime = Date.now();
              setChatItems((prev) => [...prev.slice(0, turnStartIndex + 1), ...turnItems]);
            }, UPDATE_THROTTLE_MS);
          }
          return;
        }
        lastUpdateTime = now;
        setChatItems((prev) => [...prev.slice(0, turnStartIndex + 1), ...turnItems]);
      };

      // Helper to finalize current text block
      const finalizeTextBlock = () => {
        if (currentTextContent) {
          const lastIdx = turnItems.length - 1;
          if (lastIdx >= 0 && turnItems[lastIdx].kind === 'assistant-text') {
            turnItems[lastIdx] = { kind: 'assistant-text', content: currentTextContent, streaming: false };
          }
          currentTextContent = '';
        }
      };

      // Add user message
      addChatItem({ kind: 'user', content: input, timestamp: new Date() });

      try {
        for await (const event of agent.run(input)) {
          switch (event.type) {
            case EventType.TEXT_DELTA: {
              const delta = event.data.delta as string;
              currentTextContent += delta;

              // Update or create streaming text block
              const lastItem = turnItems[turnItems.length - 1];
              if (lastItem?.kind === 'assistant-text' && lastItem.streaming) {
                turnItems[turnItems.length - 1] = {
                  kind: 'assistant-text',
                  content: currentTextContent,
                  streaming: true,
                };
              } else {
                turnItems.push({
                  kind: 'assistant-text',
                  content: currentTextContent,
                  streaming: true,
                });
              }
              updateChat();
              break;
            }

            case EventType.TOOL_CALL: {
              finalizeTextBlock();

              const id = event.data.id as string;
              const name = event.data.name as string;
              const args = event.data.args as Record<string, unknown>;
              const denied = event.data.denied as boolean | undefined;
              const streaming = event.data.streaming as boolean | undefined;

              // Check if tool already exists (from streaming start)
              const existingIndex = turnItems.findIndex(
                (item) => item.kind === 'tool' && item.toolCall.id === id
              );

              const toolCall: ToolCall = {
                id,
                name,
                args,
                pending: !denied,
                error: denied ? 'Denied by permissions' : undefined,
                streaming: streaming ?? false,
              };

              if (existingIndex >= 0) {
                // Update existing tool call
                turnItems[existingIndex] = { kind: 'tool', toolCall };
              } else {
                // Add new tool call
                turnItems.push({ kind: 'tool', toolCall });
              }
              updateChat();
              break;
            }

            case EventType.TOOL_INPUT_DELTA: {
              const id = event.data.id as string;
              const inputText = event.data.inputText as string;

              turnItems = turnItems.map((item) => {
                if (item.kind === 'tool' && item.toolCall.id === id) {
                  return {
                    kind: 'tool' as const,
                    toolCall: { ...item.toolCall, inputText, streaming: true },
                  };
                }
                return item;
              });
              updateChat();
              break;
            }

            case EventType.TOOL_RESULT: {
              const id = event.data.id as string;
              const result = event.data.result;

              turnItems = turnItems.map((item) => {
                if (item.kind === 'tool' && item.toolCall.id === id) {
                  return {
                    kind: 'tool' as const,
                    toolCall: { ...item.toolCall, pending: false, streaming: false, result },
                  };
                }
                return item;
              });
              updateChat(true); // Force update on tool complete
              break;
            }

            case EventType.APPROVAL_REQUIRED: {
              finalizeTextBlock();

              const id = event.data.id as string;
              const name = event.data.name as string;
              const args = event.data.args as Record<string, unknown>;

              setPendingApproval({ id, name, args });

              // Check if tool already exists (from streaming start)
              const existingIndex = turnItems.findIndex(
                (item) => item.kind === 'tool' && item.toolCall.id === id
              );

              const toolCall: ToolCall = { id, name, args, pending: true, streaming: false };

              if (existingIndex >= 0) {
                turnItems[existingIndex] = { kind: 'tool', toolCall };
              } else {
                turnItems.push({ kind: 'tool', toolCall });
              }
              updateChat();
              break;
            }

            case EventType.RESPONSE_METADATA: {
              const usage = event.data.usage as Record<string, number> | undefined;
              if (usage) {
                setTokenUsage((prev) => ({
                  input: prev.input + (usage.input || 0),
                  output: prev.output + (usage.output || 0),
                  total: prev.total + (usage.total || 0),
                  cacheRead: prev.cacheRead,
                  cacheCreation: prev.cacheCreation,
                }));
              }
              break;
            }

            case EventType.ERROR: {
              const error = event.data.error as string;
              turnItems.push({ kind: 'error', content: error, timestamp: new Date() });
              updateChat();
              break;
            }

            case EventType.SUBAGENT_START: {
              const subagentId = event.data.subagentId as string;
              const agentType = event.data.agentType as string;
              const task = event.data.task as string;

              setActiveSubagents((prev) => {
                const next = new Map(prev);
                next.set(subagentId, {
                  id: subagentId,
                  agentType,
                  task,
                  toolCount: 0,
                  tokenCount: 0,
                  currentTool: null,
                  status: 'running',
                });
                return next;
              });
              break;
            }

            case EventType.SUBAGENT_ACTIVITY: {
              const subagentId = event.data.subagentId as string;
              const toolDescription = event.data.toolDescription as string | null;
              const isToolStart = event.data.isToolStart as boolean;
              const isToolEnd = event.data.isToolEnd as boolean;
              const tokens = event.data.tokens as number || 0;

              setActiveSubagents((prev) => {
                const subagent = prev.get(subagentId);
                if (!subagent) return prev;

                const next = new Map(prev);
                const updates: Partial<SubagentInfo> = {};

                if (isToolStart && toolDescription) {
                  updates.currentTool = toolDescription;
                  updates.toolCount = subagent.toolCount + 1;
                }

                if (isToolEnd) {
                  // Keep showing last tool briefly, then clear
                  // For now just leave it showing
                }

                if (tokens > 0) {
                  updates.tokenCount = subagent.tokenCount + tokens;
                }

                next.set(subagentId, { ...subagent, ...updates });
                return next;
              });
              break;
            }

            case EventType.SUBAGENT_COMPLETE: {
              const subagentId = event.data.subagentId as string;

              setActiveSubagents((prev) => {
                const subagent = prev.get(subagentId);
                if (!subagent) return prev;

                const next = new Map(prev);
                next.set(subagentId, {
                  ...subagent,
                  currentTool: null,
                  status: 'complete',
                });
                return next;
              });
              break;
            }

            case EventType.SUBAGENT_ERROR: {
              const subagentId = event.data.subagentId as string;

              setActiveSubagents((prev) => {
                const subagent = prev.get(subagentId);
                if (!subagent) return prev;

                const next = new Map(prev);
                next.set(subagentId, {
                  ...subagent,
                  status: 'error',
                });
                return next;
              });
              break;
            }
          }
        }

        // Finalize any remaining text
        finalizeTextBlock();
        updateChat(true); // Force final update
      } catch (error) {
        turnItems.push({
          kind: 'error',
          content: error instanceof Error ? error.message : String(error),
          timestamp: new Date(),
        });
        updateChat(true); // Force update on error
      } finally {
        setIsProcessing(false);
      }
    },
    [showWelcome, chatItems.length, agent, addChatItem, handleSlashCommand]
  );

  const modelDisplay = `${config.model.provider}/${config.model.model}`;

  return (
    <Box flexDirection="column">
      {showWelcome && (
        <WelcomeBanner model={modelDisplay} cwd={process.cwd()} />
      )}

      <ChatDisplay
        items={chatItems}
        isLoading={isProcessing && chatItems.length === 0}
      />

      <TurnEnvelope active={isProcessing} tokens={tokenUsage} />

      {/* Active subagents panel - Claude Code style */}
      <SubagentPanel subagents={Array.from(activeSubagents.values())} />

      {pendingApproval && (
        <ApprovalDialog
          tool={pendingApproval}
          onApprove={() => handleApprovalResponse(true)}
          onDeny={() => handleApprovalResponse(false)}
          onAlways={() => handleApprovalResponse(true, true)}
        />
      )}

      <ChatInput onSubmit={handleSubmit} disabled={isProcessing} />

      <StatusBar
        model={modelDisplay}
        tokens={tokenUsage}
      />
    </Box>
  );
};
