#!/usr/bin/env python3
"""
Custom Tools, Hooks & Tool Approval.

Shows:
- Registering custom tools (sync and async callables)
- Pre/post tool hooks (block, modify, audit)
- Tool approval flow via REST (human-in-the-loop)
- Sandbox enforcement hook

Usage:
    uvicorn examples.api.tools_hooks_approval:app --reload --port 8002

    # Chat (will use custom tools when relevant)
    curl -N -X POST http://localhost:8002/chat \
      -H "Content-Type: application/json" \
      -d '{"message": "Look up the weather in San Francisco"}'

    # Check pending tool approvals
    curl http://localhost:8002/approvals

    # Approve a pending tool call
    curl -X POST http://localhost:8002/approvals/APPROVAL_ID/approve

    # Deny a pending tool call
    curl -X POST http://localhost:8002/approvals/APPROVAL_ID/deny

    # View audit log
    curl http://localhost:8002/audit
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from vel_harness import (
    HookMatcher,
    HookResult,
    PostToolUseEvent,
    PreToolUseEvent,
    VelHarness,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="vel-harness Tools, Hooks & Approval")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------------------
# Custom tools — the harness will make these available to the agent
# ---------------------------------------------------------------------------


def weather_lookup(city: str, units: str = "celsius") -> dict:
    """Look up current weather for a city."""
    # Stub — replace with a real API call
    return {
        "city": city,
        "temperature": 18 if units == "celsius" else 64,
        "units": units,
        "condition": "partly cloudy",
        "humidity": 65,
    }


async def knowledge_base_search(query: str, max_results: int = 3) -> dict:
    """Search the internal knowledge base for relevant articles."""
    # Stub — replace with a real vector search
    return {
        "query": query,
        "results": [
            {"title": f"Article about {query}", "snippet": f"Overview of {query}...", "score": 0.92},
            {"title": f"{query} best practices", "snippet": f"When working with {query}...", "score": 0.85},
        ][:max_results],
    }


def create_ticket(title: str, description: str, priority: str = "medium") -> dict:
    """Create a support ticket in the ticketing system."""
    return {
        "ticket_id": f"TKT-{int(time.time()) % 100000}",
        "title": title,
        "priority": priority,
        "status": "open",
        "created": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Hooks — intercept tool calls for auditing, blocking, and modification
# ---------------------------------------------------------------------------

audit_log: List[Dict[str, Any]] = []


async def audit_all_tools(event: PostToolUseEvent) -> None:
    """Post-hook: log every tool execution for auditing."""
    audit_log.append({
        "tool": event.tool_name,
        "input": event.tool_input,
        "duration_ms": event.duration_ms,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def block_dangerous_writes(event: PreToolUseEvent) -> HookResult:
    """Pre-hook: block writes to sensitive paths."""
    target = event.tool_input.get("path", "") or event.tool_input.get("filename", "")
    blocked_patterns = ["/etc/", "/usr/", ".env", "credentials", "secret"]
    for pattern in blocked_patterns:
        if pattern in target.lower():
            return HookResult(decision="deny", reason=f"Write to '{target}' blocked by security policy")
    return HookResult(decision="allow")


async def redact_api_keys(event: PreToolUseEvent) -> HookResult:
    """Pre-hook: redact API keys from execute commands."""
    command = event.tool_input.get("command", "")
    if "API_KEY" in command or "SECRET" in command:
        return HookResult(
            decision="modify",
            updated_input={**event.tool_input, "command": "[REDACTED — command contained secrets]"},
            reason="Redacted secrets from command",
        )
    return HookResult(decision="allow")


# ---------------------------------------------------------------------------
# Build harness with custom tools + hooks
# ---------------------------------------------------------------------------


def on_approval_needed(pending):
    """Called when a tool needs human approval."""
    logger.info(f"Approval needed: {pending.tool_name}({pending.args}) — id={pending.id}")


harness = VelHarness(
    model={
        "provider": "anthropic",
        "model": "claude-sonnet-4-5-20250929",
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
    },
    tools=[weather_lookup, knowledge_base_search, create_ticket],
    sandbox=True,
    planning=True,
    hooks={
        "pre_tool_use": [
            # Block writes to sensitive paths (targets write_file and edit_file)
            HookMatcher(matcher="write_file|edit_file", handler=block_dangerous_writes),
            # Redact secrets from execute commands
            HookMatcher(matcher="execute|execute_python", handler=redact_api_keys),
        ],
        "post_tool_use": [
            # Audit every tool call (matcher=None matches all tools)
            HookMatcher(matcher=None, handler=audit_all_tools),
        ],
    },
)

# Wire up approval notifications
harness.approval_manager.on_approval_needed(on_approval_needed)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/chat")
async def chat_stream(req: ChatRequest):
    """Stream a response. The agent can call custom tools, which go through hooks."""

    async def event_generator():
        async for event in harness.run_stream(req.message, session_id=req.session_id):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/approvals")
async def list_approvals():
    """List all pending tool approval requests."""
    pending = harness.approval_manager.get_pending()
    return {
        "pending_count": len(pending),
        "approvals": [
            {
                "id": p.id,
                "tool_name": p.tool_name,
                "args": p.args,
                "timestamp": p.timestamp.isoformat(),
            }
            for p in pending
        ],
    }


@app.post("/approvals/{approval_id}/approve")
async def approve_tool(approval_id: str):
    """Approve a pending tool call, allowing it to execute."""
    if not harness.approval_manager.respond(approval_id, approved=True):
        raise HTTPException(404, "Approval not found or already resolved")
    return {"approved": approval_id}


@app.post("/approvals/{approval_id}/deny")
async def deny_tool(approval_id: str):
    """Deny a pending tool call, blocking execution."""
    if not harness.approval_manager.respond(approval_id, approved=False):
        raise HTTPException(404, "Approval not found or already resolved")
    return {"denied": approval_id}


@app.get("/audit")
async def get_audit_log():
    """View the tool execution audit log (populated by post-tool hook)."""
    return {"entries": audit_log, "total": len(audit_log)}


@app.delete("/audit")
async def clear_audit_log():
    """Clear the audit log."""
    audit_log.clear()
    return {"cleared": True}
