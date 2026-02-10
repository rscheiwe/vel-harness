/**
 * Slash Commands
 */

import type { AgentRunner } from '../agent/runner.js';
import type { Config, Message } from '../config/types.js';

export interface CommandResult {
  success: boolean;
  message?: string;
  data?: Record<string, unknown>;
  shouldExit?: boolean;
}

export interface CommandContext {
  agent: AgentRunner;
  config: Config;
  addMessage: (msg: Message) => void;
  clearMessages: () => void;
}

export interface Command {
  name: string;
  description: string;
  aliases?: string[];
  execute(args: string[], context: CommandContext): Promise<CommandResult>;
}

// ============ Commands ============

const helpCommand: Command = {
  name: 'help',
  description: 'Show available commands',
  aliases: ['h', '?'],
  async execute() {
    const helpText = commands
      .map((c) => `  /${c.name.padEnd(12)} - ${c.description}`)
      .join('\n');
    return {
      success: true,
      message: `Available Commands:\n\n${helpText}`,
    };
  },
};

const clearCommand: Command = {
  name: 'clear',
  description: 'Clear chat display',
  aliases: ['cls'],
  async execute(args, context) {
    context.clearMessages();
    return { success: true, message: 'Chat cleared' };
  },
};

const resetCommand: Command = {
  name: 'reset',
  description: 'Reset session',
  async execute(args, context) {
    context.agent.resetSession();
    context.clearMessages();
    return {
      success: true,
      message: 'Session reset. Starting fresh conversation.',
    };
  },
};

const copyCommand: Command = {
  name: 'copy',
  description: 'Copy last response to clipboard',
  aliases: ['cp'],
  async execute(args, context) {
    const lastMessage = context.agent.getLastAssistantMessage();
    if (!lastMessage) {
      return { success: false, message: 'No assistant message to copy' };
    }

    try {
      // Dynamic import for ESM clipboard
      const { default: clipboard } = await import('clipboardy');
      await clipboard.write(lastMessage);
      return { success: true, message: 'Copied to clipboard' };
    } catch {
      return { success: false, message: 'Failed to copy to clipboard' };
    }
  },
};

const tokensCommand: Command = {
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

const permissionsCommand: Command = {
  name: 'permissions',
  description: 'Show tool permissions',
  aliases: ['perms'],
  async execute(args, context) {
    const permissions = context.agent.getPermissions();

    const lines = ['Tool Permissions:', ''];

    if (permissions.allow.length > 0) {
      lines.push('Allow:');
      permissions.allow.forEach((p) => lines.push(`  - ${p}`));
    }

    if (permissions.deny.length > 0) {
      lines.push('Deny:');
      permissions.deny.forEach((p) => lines.push(`  - ${p}`));
    }

    if (permissions.ask.length > 0) {
      lines.push('Ask:');
      permissions.ask.forEach((p) => lines.push(`  - ${p}`));
    }

    if (
      permissions.allow.length === 0 &&
      permissions.deny.length === 0 &&
      permissions.ask.length === 0
    ) {
      lines.push('No custom permissions configured.');
      lines.push('Use "Always Allow" in approval dialog to add permissions.');
    }

    return { success: true, message: lines.join('\n') };
  },
};

const configCommand: Command = {
  name: 'config',
  description: 'Show current configuration',
  async execute(args, context) {
    const c = context.config;
    return {
      success: true,
      message: `Configuration:
  Model:      ${c.model.provider}/${c.model.model}
  Max Turns:  ${c.maxTurns}
  Sandbox:    ${c.sandboxEnabled}
  Tool Calls: ${c.showToolCalls}
  Compact:    ${c.compactMode}
  Global Dir: ${c.globalDir}
  Project:    ${c.projectDir || '(none)'}`,
    };
  },
};

const exitCommand: Command = {
  name: 'exit',
  description: 'Exit the CLI',
  aliases: ['quit', 'q'],
  async execute() {
    return { success: true, shouldExit: true };
  },
};

// ============ Registry ============

const commands: Command[] = [
  helpCommand,
  clearCommand,
  resetCommand,
  copyCommand,
  tokensCommand,
  permissionsCommand,
  configCommand,
  exitCommand,
];

export function getCommand(name: string): Command | undefined {
  return commands.find(
    (c) => c.name === name || c.aliases?.includes(name)
  );
}

export function getAllCommands(): Command[] {
  return [...commands];
}

export async function executeCommand(
  command: Command,
  args: string[],
  context: CommandContext
): Promise<CommandResult> {
  return command.execute(args, context);
}
