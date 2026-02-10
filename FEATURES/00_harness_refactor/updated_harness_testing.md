You have two pieces: your Python API (FastAPI with harness) and Next.js frontend. Here's the setup:

## Backend Endpoint (FastAPI)

```python
# api/routes/harness.py
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from vel_harness import VelHarness
import json

router = APIRouter()

harness = VelHarness(
    model={"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    skill_dirs=[Path("./skills")],
)

@router.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    message = messages[-1]["content"] if messages else ""
    session_id = body.get("sessionId", "default")
    
    async def stream():
        async for event in harness.run_stream(message, session_id):
            # Vercel AI SDK expects this format
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )
```

## Frontend (Next.js with Vercel AI SDK)

```bash
npm install ai
```

```tsx
// app/test-harness/page.tsx
"use client";

import { useChat } from "ai/react";
import { useState } from "react";

export default function HarnessTest() {
  const [sessionId] = useState(() => crypto.randomUUID());
  
  const { messages, input, handleInputChange, handleSubmit, isLoading } = useChat({
    api: "http://localhost:8000/api/chat",  // Your FastAPI backend
    body: { sessionId },
  });

  return (
    <div className="max-w-4xl mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4">Harness Test</h1>
      
      {/* Messages */}
      <div className="space-y-4 mb-4 max-h-[600px] overflow-y-auto">
        {messages.map((m) => (
          <div
            key={m.id}
            className={`p-4 rounded ${
              m.role === "user" ? "bg-blue-100" : "bg-gray-100"
            }`}
          >
            <div className="font-semibold">{m.role}</div>
            <div className="whitespace-pre-wrap">{m.content}</div>
            
            {/* Show tool invocations */}
            {m.toolInvocations?.map((tool) => (
              <div key={tool.toolCallId} className="mt-2 p-2 bg-yellow-50 rounded text-sm">
                <div className="font-mono">Tool: {tool.toolName}</div>
                <div className="font-mono text-xs">
                  Input: {JSON.stringify(tool.args, null, 2)}
                </div>
                {tool.result && (
                  <div className="font-mono text-xs mt-1">
                    Result: {typeof tool.result === 'string' 
                      ? tool.result.slice(0, 500) 
                      : JSON.stringify(tool.result).slice(0, 500)}
                  </div>
                )}
              </div>
            ))}
          </div>
        ))}
        
        {isLoading && (
          <div className="p-4 bg-gray-50 rounded animate-pulse">
            Thinking...
          </div>
        )}
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          value={input}
          onChange={handleInputChange}
          placeholder="Test the harness..."
          className="flex-1 p-2 border rounded"
        />
        <button
          type="submit"
          disabled={isLoading}
          className="px-4 py-2 bg-blue-500 text-white rounded disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
```

## Meaningful Test Cases

Create a test checklist page:

```tsx
// app/test-harness/cases/page.tsx
"use client";

import { useChat } from "ai/react";
import { useState } from "react";

const TEST_CASES = [
  {
    name: "Basic Tool Use",
    prompt: "List the files in the current directory",
    expects: ["Bash tool called", "File list returned"],
  },
  {
    name: "Skill Loading", 
    prompt: "Load the code-review skill and tell me what it contains",
    expects: ["Skill tool called", "<skill-loaded> in response"],
  },
  {
    name: "Subagent - Explore",
    prompt: "Use an explore agent to find all Python files and summarize the project structure",
    expects: ["Task tool called with agent='explore'", "Structured response"],
  },
  {
    name: "Subagent - Plan",
    prompt: "Use a plan agent to create a step-by-step plan for adding user authentication",
    expects: ["Task tool called with agent='plan'", "TodoWrite or structured plan"],
  },
  {
    name: "Multi-step Task",
    prompt: "Read the README.md file, summarize it, then create a new file called SUMMARY.md with your summary",
    expects: ["ReadFile called", "Write called", "Multi-turn tool use"],
  },
  {
    name: "Context Continuity",
    prompt: "What was the first thing I asked you?",  // Run after other tests
    expects: ["References previous conversation"],
  },
  {
    name: "Todo Planning",
    prompt: "Create a todo list for refactoring a legacy codebase",
    expects: ["TodoWrite tool called", "Structured todos returned"],
  },
];

export default function TestCases() {
  const [sessionId] = useState(() => crypto.randomUUID());
  const [results, setResults] = useState<Record<string, 'pass' | 'fail' | 'pending'>>({});
  
  const { messages, append, isLoading } = useChat({
    api: "http://localhost:8000/api/chat",
    body: { sessionId },
  });

  const runTest = async (testCase: typeof TEST_CASES[0]) => {
    setResults(r => ({ ...r, [testCase.name]: 'pending' }));
    await append({ role: "user", content: testCase.prompt });
    // Manual verification needed - mark pass/fail in UI
  };

  return (
    <div className="max-w-6xl mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4">Harness Test Suite</h1>
      
      <div className="grid grid-cols-2 gap-4">
        {/* Test Cases */}
        <div className="space-y-2">
          <h2 className="font-semibold">Test Cases</h2>
          {TEST_CASES.map((tc) => (
            <div key={tc.name} className="p-3 border rounded">
              <div className="flex justify-between items-center">
                <span className="font-medium">{tc.name}</span>
                <button
                  onClick={() => runTest(tc)}
                  disabled={isLoading}
                  className="px-2 py-1 text-sm bg-blue-500 text-white rounded"
                >
                  Run
                </button>
              </div>
              <div className="text-sm text-gray-600 mt-1">{tc.prompt}</div>
              <div className="text-xs text-gray-400 mt-1">
                Expects: {tc.expects.join(", ")}
              </div>
            </div>
          ))}
        </div>

        {/* Results */}
        <div className="space-y-2">
          <h2 className="font-semibold">Output</h2>
          <div className="h-[600px] overflow-y-auto border rounded p-2">
            {messages.map((m) => (
              <div key={m.id} className="mb-4 text-sm">
                <div className="font-semibold">{m.role}:</div>
                <pre className="whitespace-pre-wrap bg-gray-50 p-2 rounded">
                  {m.content}
                </pre>
                {m.toolInvocations?.map((t) => (
                  <div key={t.toolCallId} className="bg-yellow-50 p-2 mt-1 rounded">
                    🔧 {t.toolName}: {JSON.stringify(t.args).slice(0, 100)}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
```

## Test Skills Directory

Create test skills:

```markdown
# skills/test-skill/SKILL.md
---
name: test-skill
description: A simple test skill to verify skill loading
---

# Test Skill

This skill was loaded successfully.

## Instructions

When this skill is loaded, respond with:
1. Confirm the skill was loaded
2. Echo back this instruction
3. Say "SKILL_TEST_PASS"
```

## Verification Checklist

| Feature | Test | Pass Criteria |
|---------|------|---------------|
| **Streaming** | Any prompt | Events stream progressively, not all at once |
| **Bash tool** | "Run `echo hello`" | Tool called, output returned |
| **File read** | "Read package.json" | File content in response |
| **File write** | "Create test.txt with 'hello'" | File created on disk |
| **Glob** | "Find all *.py files" | File list returned |
| **Grep** | "Search for 'def ' in *.py" | Matches returned |
| **Skill load** | "Load the test-skill" | `<skill-loaded>` in tool result |
| **Subagent** | "Use explore agent to..." | Task tool with agent param |
| **Session** | Multiple messages | Context maintained |
| **TodoWrite** | "Create a todo list for..." | Structured todos |

## Quick Smoke Test Script

```bash
# test_harness.sh
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Run echo hello and tell me the output"}]}' \
  --no-buffer

# Should stream events with Bash tool use
```

This gives you a frontend to manually test + structured test cases to verify each harness capability works.