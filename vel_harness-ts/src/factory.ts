/**
 * Factory Functions
 *
 * Convenience functions for creating harness instances.
 */

import type { ModelConfig } from 'vel-ts';
import { VelHarness } from './harness.js';
import type { HarnessConfig } from './types/config.js';
import { RESEARCH_SYSTEM_PROMPT, CODING_SYSTEM_PROMPT } from './prompts/system.js';

/**
 * Default model configuration
 */
const DEFAULT_MODEL: ModelConfig = {
  provider: 'anthropic',
  model: 'claude-sonnet-4-20250514',
};

/**
 * Create a VelHarness with sensible defaults
 */
export function createHarness(config?: Partial<HarnessConfig>): VelHarness {
  return new VelHarness({
    model: config?.model ?? DEFAULT_MODEL,
    planning: true,
    ...config,
  });
}

/**
 * Create a research-focused harness
 */
export function createResearchHarness(config?: Partial<HarnessConfig>): VelHarness {
  return new VelHarness({
    model: config?.model ?? DEFAULT_MODEL,
    planning: true,
    systemPrompt: RESEARCH_SYSTEM_PROMPT,
    ...config,
  });
}

/**
 * Create a coding-focused harness
 */
export function createCodingHarness(
  workingDirectory?: string,
  config?: Partial<HarnessConfig>
): VelHarness {
  return new VelHarness({
    model: config?.model ?? DEFAULT_MODEL,
    workingDirectory,
    planning: true,
    sandbox: true,
    systemPrompt: CODING_SYSTEM_PROMPT,
    ...config,
  });
}

/**
 * Create a minimal harness (no skills, no planning)
 */
export function createMinimalHarness(config?: Partial<HarnessConfig>): VelHarness {
  return new VelHarness({
    model: config?.model ?? DEFAULT_MODEL,
    planning: false,
    ...config,
  });
}
