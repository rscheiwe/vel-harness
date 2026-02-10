/**
 * Basic Usage Example
 *
 * Demonstrates the simplest usage of VelHarness.
 */

import { createHarness } from '../src/index.js';

async function main() {
  // Create a harness with default settings
  const harness = createHarness({
    model: { provider: 'anthropic', model: 'claude-sonnet-4-5-20250929' },
  });

  // Simple non-streaming usage
  console.log('=== Non-Streaming ===\n');
  const response = await harness.run('What is 2 + 2?');
  console.log('Response:', response);

  // Streaming usage
  console.log('\n=== Streaming ===\n');
  for await (const event of harness.runStream('Count from 1 to 5')) {
    if (event.type === 'text-delta') {
      process.stdout.write(event.delta);
    }
  }
  console.log('\n');

  // With session for multi-turn
  console.log('=== Multi-turn Session ===\n');
  const sessionId = 'example-session';

  await harness.run('My name is Alice', { sessionId });
  const nameResponse = await harness.run('What is my name?', { sessionId });
  console.log('Name response:', nameResponse);
}

main().catch(console.error);
