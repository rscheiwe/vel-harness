#!/usr/bin/env python3
"""
Sessions, Model Switching & Reasoning Modes.

Shows:
- HarnessSession with persistent conversation history
- Model hot-switching mid-conversation (sonnet → haiku → opus)
- Reasoning modes: native, prompted, reflection, none
- Session interrupt
- Session state inspection

Usage:
    uvicorn examples.api.sessions_and_models:app --reload --port 8001

    # Start a session
    curl -N -X POST http://localhost:8001/sessions/my-session/chat \
      -H "Content-Type: application/json" \
      -d '{"message": "Remember: my name is Alice"}'

    # Continue the same session (history preserved)
    curl -N -X POST http://localhost:8001/sessions/my-session/chat \
      -H "Content-Type: application/json" \
      -d '{"message": "What is my name?"}'

    # Switch model mid-session
    curl -X POST http://localhost:8001/sessions/my-session/model \
      -H "Content-Type: application/json" \
      -d '{"model": "haiku"}'

    # Enable extended thinking
    curl -X POST http://localhost:8001/sessions/my-session/reasoning \
      -H "Content-Type: application/json" \
      -d '{"mode": "native", "budget_tokens": 8000}'

    # Get session state
    curl http://localhost:8001/sessions/my-session/state

    # Interrupt a running query
    curl -X POST http://localhost:8001/sessions/my-session/interrupt
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional, Union

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from vel_harness import HarnessSession, ReasoningConfig, VelHarness

app = FastAPI(title="vel-harness Sessions & Models")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

harness = VelHarness(
    model={
        "provider": "anthropic",
        "model": "claude-sonnet-4-5-20250929",
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
    },
    sandbox=True,
    planning=True,
)

# Active sessions — in production use Redis or a database
sessions: Dict[str, HarnessSession] = {}


def get_or_create_session(session_id: str) -> HarnessSession:
    if session_id not in sessions:
        sessions[session_id] = harness.create_session(session_id=session_id)
    return sessions[session_id]


# --- Request/Response models ---


class ChatRequest(BaseModel):
    message: str


class ModelRequest(BaseModel):
    model: str  # "sonnet", "opus", "haiku", or full model dict


class ReasoningRequest(BaseModel):
    mode: str  # "native", "prompted", "reflection", "none"
    budget_tokens: Optional[int] = None
    max_refinements: Optional[int] = None
    transient: Optional[bool] = None


# --- Endpoints ---


@app.post("/sessions/{session_id}/chat")
async def session_chat(session_id: str, req: ChatRequest):
    """Stream a response within a persistent session."""
    session = get_or_create_session(session_id)

    async def event_generator():
        async for event in session.query(req.message):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/sessions/{session_id}/chat/sync")
async def session_chat_sync(session_id: str, req: ChatRequest):
    """Non-streaming session chat."""
    session = get_or_create_session(session_id)
    result = await session.run(req.message)
    return {
        "response": result,
        "session_id": session_id,
        "query_count": session.query_count,
        "model": session.model,
    }


@app.post("/sessions/{session_id}/model")
async def switch_model(session_id: str, req: ModelRequest):
    """Hot-switch the model for an existing session.

    Accepts shorthand: "sonnet", "opus", "haiku"
    or a full model identifier string.
    """
    session = get_or_create_session(session_id)
    session.set_model(req.model)
    return {"session_id": session_id, "model": session.model}


@app.post("/sessions/{session_id}/reasoning")
async def set_reasoning(session_id: str, req: ReasoningRequest):
    """Change reasoning mode between queries.

    Modes:
    - "native": Anthropic extended thinking (budget_tokens controls depth)
    - "prompted": Provider-agnostic CoT via <thinking> tags
    - "reflection": Multi-pass refinement
    - "none": Standard execution
    """
    session = get_or_create_session(session_id)

    config_dict: Dict[str, Union[str, int, bool, None]] = {"mode": req.mode}
    if req.budget_tokens is not None:
        config_dict["budget_tokens"] = req.budget_tokens
    if req.max_refinements is not None:
        config_dict["max_refinements"] = req.max_refinements
    if req.transient is not None:
        config_dict["transient"] = req.transient

    session.set_reasoning(ReasoningConfig.from_value(config_dict))
    return {"session_id": session_id, "reasoning": config_dict}


@app.post("/sessions/{session_id}/interrupt")
async def interrupt_session(session_id: str):
    """Interrupt a running query. The stream will yield an 'interrupted' event."""
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    sessions[session_id].interrupt()
    return {"session_id": session_id, "interrupted": True}


@app.get("/sessions/{session_id}/state")
async def session_state(session_id: str):
    """Inspect session state: query count, model, checkpoints, changed files."""
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    return sessions[session_id].get_state()


@app.get("/sessions")
async def list_sessions():
    """List all active sessions with summary info."""
    return {
        sid: {
            "query_count": s.query_count,
            "model": s.model,
            "is_interrupted": s.is_interrupted,
        }
        for sid, s in sessions.items()
    }


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Remove a session (frees memory)."""
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    del sessions[session_id]
    return {"deleted": session_id}
