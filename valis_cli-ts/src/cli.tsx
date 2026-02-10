#!/usr/bin/env node

/**
 * Valis CLI Entry Point
 */

import { config as loadEnv } from 'dotenv';
import * as fs from 'fs';
import * as path from 'path';

// Walk up directory tree to find and load .env files
function loadEnvFiles(): void {
  let dir = process.cwd();
  const root = path.parse(dir).root;

  while (dir !== root) {
    const envPath = path.join(dir, '.env');
    if (fs.existsSync(envPath)) {
      loadEnv({ path: envPath });
    }
    dir = path.dirname(dir);
  }
}

loadEnvFiles();

import React from 'react';
import { render } from 'ink';
import { Command } from 'commander';
import { App } from './components/App.js';
import { getConfig } from './config/index.js';

const program = new Command();

program
  .name('valis-cli')
  .description('Valis CLI - AI agent assistant')
  .version('1.0.0')
  .option('-m, --model <model>', 'Model to use (e.g., claude-sonnet-4-5-20250929)')
  .option('-p, --provider <provider>', 'Provider (anthropic, openai)')
  .option('--no-sandbox', 'Disable sandbox mode')
  .option('--compact', 'Compact display mode')
  .option('--no-tool-calls', 'Hide tool call display')
  .action(async (options) => {
    const config = getConfig();

    // Apply CLI options
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
    if (options.toolCalls === false) {
      config.showToolCalls = false;
    }

    // Render the app (normal terminal mode - terminal handles scrolling)
    const { waitUntilExit } = render(<App config={config} />);

    await waitUntilExit();
  });

program.parse();
