/**
 * Configuration Management
 */

import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import type { Config, ModelSettings, ApprovalSettings, Permissions, ContentBlock, ToolCall, Message, TokenUsage, ToolApproval, ChatItem } from './types.js';

const DEFAULT_GLOBAL_DIR = path.join(os.homedir(), '.valis');
const DEFAULT_PROJECT_DIR = '.valis';
const DEFAULT_CONFIG_FILE = 'config.json';
const DEFAULT_SETTINGS_FILE = 'settings.local.json';

const DEFAULT_MODEL: ModelSettings = {
  provider: 'anthropic',
  model: 'claude-sonnet-4-20250514',
};

const DEFAULT_APPROVAL: ApprovalSettings = {
  requireApproval: true,
  autoApprove: [
    'glob',
    'grep',
    'list_skills',
    'get_skill',
  ],
  alwaysDeny: [],
};

/**
 * Detect project-specific .valis directory
 */
export function detectProjectDir(startPath?: string): string | undefined {
  let current = path.resolve(startPath || process.cwd());
  const root = path.parse(current).root;

  while (current !== root) {
    const valisDir = path.join(current, DEFAULT_PROJECT_DIR);
    if (fs.existsSync(valisDir) && fs.statSync(valisDir).isDirectory()) {
      return valisDir;
    }

    // Also check for AGENTS.md as indicator
    const agentsFile = path.join(current, 'AGENTS.md');
    if (fs.existsSync(agentsFile)) {
      // Create .valis dir if AGENTS.md exists
      fs.mkdirSync(valisDir, { recursive: true });
      return valisDir;
    }

    current = path.dirname(current);
  }

  return undefined;
}

/**
 * Load configuration from file
 */
export function loadConfigFile(configPath: string): Partial<Config> {
  if (!fs.existsSync(configPath)) {
    return {};
  }

  try {
    const data = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
    return {
      model: data.model ? {
        provider: data.model.provider || DEFAULT_MODEL.provider,
        model: data.model.model || DEFAULT_MODEL.model,
        temperature: data.model.temperature,
        maxTokens: data.model.maxTokens,
      } : undefined,
      approval: data.approval ? {
        requireApproval: data.approval.requireApproval ?? true,
        autoApprove: data.approval.autoApprove || [],
        alwaysDeny: data.approval.alwaysDeny || [],
      } : undefined,
      agentName: data.agentName,
      maxTurns: data.maxTurns,
      sandboxEnabled: data.sandboxEnabled,
      showThinking: data.showThinking,
      showToolCalls: data.showToolCalls,
      compactMode: data.compactMode,
    };
  } catch {
    return {};
  }
}

/**
 * Get configuration with project detection
 */
export function getConfig(options?: {
  projectDir?: string;
  globalDir?: string;
}): Config {
  const globalDir = options?.globalDir || DEFAULT_GLOBAL_DIR;
  const projectDir = options?.projectDir || detectProjectDir();

  // Ensure global dir exists
  fs.mkdirSync(globalDir, { recursive: true });

  // Load from file if exists
  const configPath = projectDir
    ? path.join(projectDir, DEFAULT_CONFIG_FILE)
    : path.join(globalDir, DEFAULT_CONFIG_FILE);

  const fileConfig = loadConfigFile(configPath);

  return {
    globalDir,
    projectDir,
    model: fileConfig.model || DEFAULT_MODEL,
    approval: fileConfig.approval || DEFAULT_APPROVAL,
    agentName: fileConfig.agentName || 'valis-agent',
    maxTurns: fileConfig.maxTurns || 50,
    sandboxEnabled: fileConfig.sandboxEnabled ?? false,
    showThinking: fileConfig.showThinking ?? false,
    showToolCalls: fileConfig.showToolCalls ?? true,
    compactMode: fileConfig.compactMode ?? false,
  };
}

/**
 * Save configuration to file
 */
export function saveConfig(config: Config): void {
  const configDir = config.projectDir || config.globalDir;
  fs.mkdirSync(configDir, { recursive: true });

  const configPath = path.join(configDir, DEFAULT_CONFIG_FILE);
  const data = {
    model: config.model,
    approval: config.approval,
    agentName: config.agentName,
    maxTurns: config.maxTurns,
    sandboxEnabled: config.sandboxEnabled,
    showThinking: config.showThinking,
    showToolCalls: config.showToolCalls,
    compactMode: config.compactMode,
  };

  fs.writeFileSync(configPath, JSON.stringify(data, null, 2));
}

/**
 * Load permissions from settings.local.json
 */
export function loadPermissions(config: Config): Permissions {
  const settingsPath = config.projectDir
    ? path.join(config.projectDir, DEFAULT_SETTINGS_FILE)
    : path.join(config.globalDir, DEFAULT_SETTINGS_FILE);

  if (!fs.existsSync(settingsPath)) {
    return { allow: [], deny: [], ask: [] };
  }

  try {
    const data = JSON.parse(fs.readFileSync(settingsPath, 'utf-8'));
    return {
      allow: data.permissions?.allow || [],
      deny: data.permissions?.deny || [],
      ask: data.permissions?.ask || [],
    };
  } catch {
    return { allow: [], deny: [], ask: [] };
  }
}

/**
 * Save permissions to settings.local.json
 */
export function savePermissions(config: Config, permissions: Permissions): void {
  // Auto-create project .valis folder if none exists
  let configDir = config.projectDir;
  if (!configDir) {
    configDir = path.join(process.cwd(), DEFAULT_PROJECT_DIR);
    fs.mkdirSync(configDir, { recursive: true });
  }

  const settingsPath = path.join(configDir, DEFAULT_SETTINGS_FILE);

  // Load existing settings
  let data: Record<string, unknown> = {};
  if (fs.existsSync(settingsPath)) {
    try {
      data = JSON.parse(fs.readFileSync(settingsPath, 'utf-8'));
    } catch {
      // Ignore parse errors
    }
  }

  data.permissions = permissions;
  fs.writeFileSync(settingsPath, JSON.stringify(data, null, 2));
}

/**
 * Check if tool matches a permission pattern
 */
export function matchesPattern(
  toolName: string,
  args: Record<string, unknown>,
  pattern: string
): boolean {
  // Parse pattern: tool_name or tool_name(args_pattern)
  const match = pattern.match(/^([^(]+)(?:\(([^)]*)\))?$/);
  if (!match) return false;

  const patternName = match[1];
  const patternArgs = match[2];

  // Simple glob-like matching for tool name
  const nameRegex = new RegExp(
    '^' + patternName.replace(/\*/g, '.*').replace(/\?/g, '.') + '$'
  );
  if (!nameRegex.test(toolName)) return false;

  // If no args pattern, tool name match is enough
  if (patternArgs === undefined) return true;

  // Any args
  if (patternArgs === '*') return true;

  // Check key=value patterns
  if (patternArgs.includes('=')) {
    for (const argPattern of patternArgs.split(',')) {
      const [key, valPattern] = argPattern.trim().split('=', 2);
      if (key && valPattern && key in args) {
        const argVal = String(args[key]);
        const valRegex = new RegExp(
          '^' + valPattern.trim().replace(/\*/g, '.*') + '$'
        );
        if (!valRegex.test(argVal)) return false;
      } else if (key && !(key in args)) {
        return false;
      }
    }
    return true;
  }

  // Check if any arg value matches pattern
  for (const val of Object.values(args)) {
    if (typeof val === 'string') {
      const valRegex = new RegExp(
        '^' + patternArgs.replace(/\*/g, '.*') + '$'
      );
      if (valRegex.test(val)) return true;
    }
  }

  return false;
}

/**
 * Check permission for a tool call
 */
export function checkPermission(
  permissions: Permissions,
  toolName: string,
  args: Record<string, unknown>
): 'allow' | 'deny' | 'ask' | null {
  // Check deny first (highest priority)
  for (const pattern of permissions.deny) {
    if (matchesPattern(toolName, args, pattern)) {
      return 'deny';
    }
  }

  // Check allow
  for (const pattern of permissions.allow) {
    if (matchesPattern(toolName, args, pattern)) {
      return 'allow';
    }
  }

  // Check ask
  for (const pattern of permissions.ask) {
    if (matchesPattern(toolName, args, pattern)) {
      return 'ask';
    }
  }

  return null;
}

export type { Config, ModelSettings, ApprovalSettings, Permissions, ContentBlock, ToolCall, Message, TokenUsage, ToolApproval, ChatItem };
