#!/usr/bin/env python3
"""
Advanced Features — Caching, Retry, Fallback, Checkpoints, Memory, Database.

Shows:
- Tool caching (cacheable tools, cache stats)
- Retry with exponential backoff + circuit breaker
- Fallback model on rate limit / server errors
- File checkpoints and rewind
- Memory middleware (persistent cross-session memory)
- Database middleware (SQL tools)
- Context management stats

Usage:
    uvicorn examples.api.advanced_features:app --reload --port 8004

    # Chat with all features enabled
    curl -N -X POST http://localhost:8004/chat \
      -H "Content-Type: application/json" \
      -d '{"message": "Read the README and summarize it"}'

    # Create a checkpoint, make changes, then rewind
    curl -X POST http://localhost:8004/sessions/my-session/checkpoint
    curl -N -X POST http://localhost:8004/chat \
      -H "Content-Type: application/json" \
      -d '{"message": "Create a file called test.txt with hello world", "session_id": "my-session"}'
    curl -X POST http://localhost:8004/sessions/my-session/rewind \
      -H "Content-Type: application/json" \
      -d '{"checkpoint_id": "CHECKPOINT_ID_FROM_ABOVE"}'

    # Cache stats
    curl http://localhost:8004/cache/stats

    # Changed files in session
    curl http://localhost:8004/sessions/my-session/changes

    # Harness state (all middleware states)
    curl http://localhost:8004/state
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from vel_harness import HarnessSession, VelHarness

app = FastAPI(title="vel-harness Advanced Features")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

harness = VelHarness(
    model={
        "provider": "anthropic",
        "model": "claude-sonnet-4-5-20250929",
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
    },
    sandbox=True,
    planning=True,
    memory=True,
    database=True,
    caching=True,
    retry=True,
    # Fallback to haiku on rate limits or 5xx errors
    fallback_model="haiku",
    max_fallback_retries=2,
    working_directory=str(Path(__file__).parent.parent.parent),
)

sessions: Dict[str, HarnessSession] = {}


def get_or_create_session(session_id: str) -> HarnessSession:
    if session_id not in sessions:
        sessions[session_id] = harness.create_session(session_id=session_id)
    return sessions[session_id]


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class CheckpointRequest(BaseModel):
    label: Optional[str] = None


class RewindRequest(BaseModel):
    checkpoint_id: str


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


@app.post("/chat")
async def chat_stream(req: ChatRequest):
    """Chat with all advanced features active.

    The agent has access to:
    - File tools with checkpoint tracking
    - SQL database tools (list_tables, describe_table, sql_query)
    - Memory tools (save_memory, recall_memory, search_memories)
    - Planning tools (write_todos)
    - Cached tool results (list_tables, describe_table auto-cached)
    - Retry with backoff on transient failures
    - Automatic fallback to haiku if sonnet is rate-limited
    """
    session = get_or_create_session(req.session_id)

    async def event_generator():
        async for event in session.query(req.message):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Checkpoints & Rewind
# ---------------------------------------------------------------------------


@app.post("/sessions/{session_id}/checkpoint")
async def create_checkpoint(session_id: str, req: CheckpointRequest = CheckpointRequest()):
    """Create a filesystem checkpoint. Returns a checkpoint_id for later rewind."""
    session = get_or_create_session(session_id)
    checkpoint_id = session.create_checkpoint(label=req.label)
    return {"checkpoint_id": checkpoint_id, "label": req.label}


@app.post("/sessions/{session_id}/rewind")
async def rewind_to_checkpoint(session_id: str, req: RewindRequest):
    """Rewind all file changes back to a checkpoint (LIFO replay)."""
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    session = sessions[session_id]
    reverted = session.rewind_files(req.checkpoint_id)
    return {"checkpoint_id": req.checkpoint_id, "reverted_files": reverted}


@app.get("/sessions/{session_id}/changes")
async def get_changed_files(session_id: str):
    """List all files changed in this session (deduplicated)."""
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    files = sessions[session_id].get_changed_files()
    return {"session_id": session_id, "changed_files": files}


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


@app.get("/cache/stats")
async def cache_stats():
    """Get tool caching statistics (hits, misses, evictions)."""
    # The caching middleware exposes stats through the harness state
    state = harness.get_state()
    caching_state = state.get("caching", {})
    return {"caching": caching_state}


# ---------------------------------------------------------------------------
# State & Introspection
# ---------------------------------------------------------------------------


@app.get("/state")
async def harness_state():
    """Full harness state — all middleware states combined."""
    return harness.get_state()


@app.get("/sessions/{session_id}/state")
async def session_state(session_id: str):
    """Session-level state: query count, model, checkpoints, changes."""
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    return sessions[session_id].get_state()


@app.get("/fallback/status")
async def fallback_status():
    """Check if fallback model is configured and its retry settings."""
    wrapper = harness.fallback_wrapper
    if wrapper is None:
        return {"configured": False}
    return {
        "configured": True,
        "fallback_model": harness.config.fallback_model,
        "max_retries": harness.config.max_fallback_retries,
    }
