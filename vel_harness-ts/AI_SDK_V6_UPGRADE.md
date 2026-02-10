# vel-ts AI SDK v6 Upgrade Handoff

## Summary

vel-ts has been upgraded from AI SDK v5 to v6 to support Claude Sonnet 4 (`claude-sonnet-4-20250514`), which requires the v3 Language Model Specification.

## Changes Made in vel-ts

1. **Upgraded packages:**
   - `ai`: 5.0.124 → 6.0.64
   - `@ai-sdk/anthropic`: 3.0.33 (latest, compatible with v6)
   - `@ai-sdk/openai`: latest
   - `@ai-sdk/google`: latest

2. **No code changes required** - vel-ts already uses v6-compatible APIs:
   - `inputSchema` (unchanged)
   - `execute` (unchanged)
   - `stepCountIs` (unchanged)
   - `generateText`, `streamText`, `tool` (unchanged)

## Impact on vel-harness-ts

**No code changes required.**

vel-harness-ts only imports from vel-ts:
- `AgentV2`
- `ModelConfig`
- `ToolSpec`
- `StreamEvent`
- `GenerationConfig`

It does NOT directly use any AI SDK APIs.

## Required Actions

Run the following to pick up the updated vel-ts:

```bash
cd /Users/richard.s/vel-harness/vel_harness-ts
rm -rf node_modules
npm install
npm run build
```

## Testing

Test with Claude Sonnet 4:

```typescript
const harness = new VelHarness({
  model: {
    provider: 'anthropic',
    model: 'claude-sonnet-4-20250514',
  },
  // ... other config
});
```

## AI SDK v5 → v6 Breaking Changes (Reference)

These changes affect AI SDK users directly, but NOT vel-harness-ts since it only uses vel-ts:

| v5 | v6 |
|---|---|
| `CoreMessage` | `ModelMessage` |
| `convertToCoreMessages()` | `await convertToModelMessages()` |
| `ToolCallOptions` | `ToolExecutionOptions` |
| `textEmbeddingModel()` | `embeddingModel()` |
| `generateObject()` / `streamObject()` | `generateText()` / `streamText()` with `output` param |

For full migration guide: https://ai-sdk.dev/docs/migration-guides/migration-guide-6-0

## Environment Variables

Ensure these are set for the respective providers:
- `ANTHROPIC_API_KEY` - for Claude models
- `OPENAI_API_KEY` - for OpenAI models
- `GOOGLE_API_KEY` - for Gemini models
