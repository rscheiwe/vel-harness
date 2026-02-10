/**
 * Skills Example
 *
 * Demonstrates skill loading and activation.
 */

import { join } from 'node:path';
import { createHarness } from '../src/index.js';

async function main() {
  // Create harness with skills directory
  const harness = createHarness({
    model: { provider: 'anthropic', model: 'claude-sonnet-4-5-20250929' },
    skillDirs: [join(import.meta.dirname, '../tests/fixtures/skills')],
  });

  // Initialize to load skills
  await harness['initialize']();

  // List available skills
  console.log('=== Available Skills ===\n');
  const skillsMiddleware = harness.getMiddleware('skills');
  if (skillsMiddleware) {
    const registry = (skillsMiddleware as any).getRegistry();
    for (const skill of registry.getAll()) {
      console.log(`- ${skill.name}: ${skill.description}`);
    }
  }

  // Run with auto-activation (triggers on "research")
  console.log('\n=== Research Query (Auto-activation) ===\n');
  const response = await harness.run(
    'I need to research the best practices for API design'
  );
  console.log('Response:', response);
}

main().catch(console.error);
