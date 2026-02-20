#!/usr/bin/env python3
"""
Full Chat Application — Production-like FastAPI app combining all features.

This is the "put it all together" example: a chat API that mirrors how Claude
works in the web browser. Multiple users, persistent sessions, streaming,
skills, subagents, custom tools, hooks, approval, checkpoints, reasoning
modes, model switching, fallback, caching, and memory.

Usage:
    uvicorn examples.api.full_chat_app:app --reload --port 8080

Endpoints:
    POST /v1/chat                        Stream a message (SSE)
    POST /v1/chat/sync                   Non-streaming message
    GET  /v1/sessions                    List active sessions
    GET  /v1/sessions/:id                Session state
    DEL  /v1/sessions/:id                Delete session
    POST /v1/sessions/:id/model          Switch model
    POST /v1/sessions/:id/reasoning      Set reasoning mode
    POST /v1/sessions/:id/interrupt      Interrupt running query
    POST /v1/sessions/:id/checkpoint     Create file checkpoint
    POST /v1/sessions/:id/rewind         Rewind to checkpoint
    GET  /v1/sessions/:id/changes        List changed files
    GET  /v1/skills                      List skills
    GET  /v1/agents                      List agent types
    POST /v1/agents/:id                  Register custom agent
    GET  /v1/approvals                   Pending tool approvals
    POST /v1/approvals/:id/respond       Approve or deny
    GET  /v1/audit                       Tool execution audit log
    GET  /v1/state                       Full harness introspection
"""

import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from vel_harness import (
    AgentDefinition,
    HarnessSession,
    HookMatcher,
    HookResult,
    PostToolUseEvent,
    PreToolUseEvent,
    ReasoningConfig,
    VelHarness,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chat-app")

# ============================================================================
# Custom tools
# ============================================================================


def web_search(query: str, max_results: int = 5) -> dict:
    """Search the web for information. Returns a list of results with titles, URLs, and snippets."""
    return {
        "query": query,
        "results": [
            {
                "title": f"Result {i+1} for: {query}",
                "url": f"https://example.com/search?q={query}&r={i+1}",
                "snippet": f"This is a stub result for '{query}'. Replace with a real search API.",
            }
            for i in range(min(max_results, 5))
        ],
    }


async def fetch_url(url: str) -> dict:
    """Fetch the content of a URL and return it as text."""
    # Stub — replace with httpx/aiohttp
    return {"url": url, "content": f"[Stub content for {url}]", "status": 200}


def calculator(expression: str) -> dict:
    """Evaluate a mathematical expression safely."""
    allowed = set("0123456789+-*/.() ")
    if not all(c in allowed for c in expression):
        return {"error": "Invalid characters in expression"}
    try:
        result = eval(expression, {"__builtins__": {}})  # noqa: S307
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"error": str(e)}


def current_time(timezone_name: str = "UTC") -> dict:
    """Get the current date and time."""
    return {"timezone": timezone_name, "datetime": datetime.now(timezone.utc).isoformat()}


# ============================================================================
# Hooks
# ============================================================================

audit_log: List[Dict[str, Any]] = []


async def audit_hook(event: PostToolUseEvent) -> None:
    """Log all tool executions."""
    audit_log.append({
        "tool": event.tool_name,
        "input": event.tool_input,
        "duration_ms": round(event.duration_ms, 2),
        "session": event.session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    if len(audit_log) > 1000:
        audit_log.pop(0)


async def guard_file_writes(event: PreToolUseEvent) -> HookResult:
    """Block writes outside the working directory."""
    path = event.tool_input.get("path", "")
    if path and (path.startswith("/etc") or path.startswith("/usr") or ".." in path):
        return HookResult(decision="deny", reason=f"Blocked write to {path}")
    return HookResult(decision="allow")


# ============================================================================
# Harness setup
# ============================================================================

skills_dir = Path(__file__).parent.parent / "skills"
working_dir = Path(__file__).parent.parent.parent

harness = VelHarness(
    model={
        "provider": "anthropic",
        "model": "claude-sonnet-4-5-20250929",
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
    },
    tools=[web_search, fetch_url, calculator, current_time],
    skill_dirs=[str(skills_dir)] if skills_dir.exists() else [],
    sandbox=True,
    planning=True,
    memory=True,
    caching=True,
    retry=True,
    fallback_model="haiku",
    max_fallback_retries=2,
    working_directory=str(working_dir),
    hooks={
        "pre_tool_use": [
            HookMatcher(matcher="write_file|edit_file", handler=guard_file_writes),
        ],
        "post_tool_use": [
            HookMatcher(matcher=None, handler=audit_hook),
        ],
    },
)

# Register extra agent types
harness.register_agent(
    "code-reviewer",
    AgentDefinition(
        description="Code review specialist",
        prompt="You are a code reviewer. Find bugs, security issues, and style problems.",
        tools=["read_file", "glob", "grep"],
        model="sonnet",
        max_turns=20,
    ),
)
harness.register_agent(
    "summarizer",
    AgentDefinition(
        description="Summarization agent — reads and condenses information",
        prompt="You summarize information concisely. Use bullet points. Be precise.",
        tools=["read_file", "glob", "grep"],
        model="haiku",
        max_turns=15,
    ),
)


# ============================================================================
# Session store
# ============================================================================

sessions: Dict[str, HarnessSession] = {}


def get_or_create_session(session_id: str) -> HarnessSession:
    if session_id not in sessions:
        sessions[session_id] = harness.create_session(session_id=session_id)
    return sessions[session_id]


# ============================================================================
# App
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Chat app starting — model=%s", harness.model)
    logger.info("Skills dir: %s", skills_dir)
    logger.info("Agent types: %s", harness.list_agent_types())
    yield
    logger.info("Chat app shutting down")
    sessions.clear()


app = FastAPI(title="vel-harness Chat App", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ============================================================================
# Request / Response models
# ============================================================================


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    context: Optional[Dict[str, Any]] = None


class SyncChatResponse(BaseModel):
    response: str
    session_id: str
    query_count: int
    model: Dict[str, Any]


class ModelRequest(BaseModel):
    model: str = Field(description="'sonnet', 'opus', 'haiku', or full model ID")


class ReasoningRequest(BaseModel):
    mode: str = Field(description="'native', 'prompted', 'reflection', 'none'")
    budget_tokens: Optional[int] = None
    max_refinements: Optional[int] = None
    transient: Optional[bool] = None


class CheckpointRequest(BaseModel):
    label: Optional[str] = None


class RewindRequest(BaseModel):
    checkpoint_id: str


class ApprovalResponse(BaseModel):
    approved: bool


class AgentDefinitionRequest(BaseModel):
    description: str = ""
    prompt: str = ""
    tools: List[str] = []
    model: Optional[str] = None
    max_turns: int = 50
    timeout: float = 300.0


# ============================================================================
# Chat endpoints
# ============================================================================


@app.post("/v1/chat")
async def chat_stream(req: ChatRequest):
    """Stream a response via SSE.

    Each line is `data: <json>\\n\\n`. Event types:
    - start, text-delta, text-end, tool-input-available, tool-output-available,
      finish, error, interrupted, reasoning-start, reasoning-delta, reasoning-end
    """
    session = get_or_create_session(req.session_id)

    async def event_generator():
        async for event in session.query(req.message, context=req.context):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/v1/chat/sync", response_model=SyncChatResponse)
async def chat_sync(req: ChatRequest):
    """Non-streaming chat — returns the complete response."""
    session = get_or_create_session(req.session_id)
    result = await session.run(req.message, context=req.context)
    return SyncChatResponse(
        response=result,
        session_id=req.session_id,
        query_count=session.query_count,
        model=session.model,
    )


# ============================================================================
# Session management
# ============================================================================


@app.get("/v1/sessions")
async def list_sessions():
    return {
        sid: {
            "query_count": s.query_count,
            "model": s.model,
            "is_interrupted": s.is_interrupted,
        }
        for sid, s in sessions.items()
    }


@app.get("/v1/sessions/{session_id}")
async def get_session(session_id: str):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    return sessions[session_id].get_state()


@app.delete("/v1/sessions/{session_id}")
async def delete_session(session_id: str):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    del sessions[session_id]
    return {"deleted": session_id}


@app.post("/v1/sessions/{session_id}/model")
async def switch_model(session_id: str, req: ModelRequest):
    session = get_or_create_session(session_id)
    session.set_model(req.model)
    return {"session_id": session_id, "model": session.model}


@app.post("/v1/sessions/{session_id}/reasoning")
async def set_reasoning(session_id: str, req: ReasoningRequest):
    session = get_or_create_session(session_id)
    config_dict = {"mode": req.mode}
    if req.budget_tokens is not None:
        config_dict["budget_tokens"] = req.budget_tokens
    if req.max_refinements is not None:
        config_dict["max_refinements"] = req.max_refinements
    if req.transient is not None:
        config_dict["transient"] = req.transient
    session.set_reasoning(ReasoningConfig.from_value(config_dict))
    return {"session_id": session_id, "reasoning": config_dict}


@app.post("/v1/sessions/{session_id}/interrupt")
async def interrupt_session(session_id: str):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    sessions[session_id].interrupt()
    return {"interrupted": True}


# ============================================================================
# Checkpoints & Rewind
# ============================================================================


@app.post("/v1/sessions/{session_id}/checkpoint")
async def create_checkpoint(session_id: str, req: CheckpointRequest = CheckpointRequest()):
    session = get_or_create_session(session_id)
    checkpoint_id = session.create_checkpoint(label=req.label)
    return {"checkpoint_id": checkpoint_id, "label": req.label}


@app.post("/v1/sessions/{session_id}/rewind")
async def rewind(session_id: str, req: RewindRequest):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    reverted = sessions[session_id].rewind_files(req.checkpoint_id)
    return {"reverted_files": reverted}


@app.get("/v1/sessions/{session_id}/changes")
async def changed_files(session_id: str):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    return {"changed_files": sessions[session_id].get_changed_files()}


# ============================================================================
# Skills
# ============================================================================


@app.get("/v1/skills")
async def list_skills():
    registry = harness.deep_agent.skills
    if registry is None:
        return {"skills": []}
    return {
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "tags": s.tags,
                "triggers": s.triggers,
                "priority": s.priority,
                "enabled": s.enabled,
            }
            for s in registry.list_all()
        ]
    }


# ============================================================================
# Agents
# ============================================================================


@app.get("/v1/agents")
async def list_agents():
    all_agents = harness.agent_registry.get_all()
    return {
        agent_id: {
            "description": c.description,
            "tools": c.tools,
            "max_turns": c.max_turns,
        }
        for agent_id, c in all_agents.items()
    }


@app.post("/v1/agents/{agent_id}")
async def register_agent(agent_id: str, req: AgentDefinitionRequest):
    harness.register_agent(
        agent_id,
        AgentDefinition(
            description=req.description,
            prompt=req.prompt,
            tools=req.tools,
            model=req.model,
            max_turns=req.max_turns,
            timeout=req.timeout,
        ),
    )
    return {"registered": agent_id}


# ============================================================================
# Approvals
# ============================================================================


@app.get("/v1/approvals")
async def list_approvals():
    pending = harness.approval_manager.get_pending()
    return {
        "pending": [
            {"id": p.id, "tool_name": p.tool_name, "args": p.args, "timestamp": p.timestamp.isoformat()}
            for p in pending
        ]
    }


@app.post("/v1/approvals/{approval_id}/respond")
async def respond_to_approval(approval_id: str, req: ApprovalResponse):
    if not harness.approval_manager.respond(approval_id, approved=req.approved):
        raise HTTPException(404, "Approval not found or already resolved")
    return {"approval_id": approval_id, "approved": req.approved}


# ============================================================================
# Audit & Introspection
# ============================================================================


@app.get("/v1/audit")
async def get_audit(limit: int = Query(50, le=1000)):
    return {"entries": audit_log[-limit:], "total": len(audit_log)}


@app.get("/v1/state")
async def harness_state():
    return harness.get_state()
