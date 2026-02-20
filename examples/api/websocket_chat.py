#!/usr/bin/env python3
"""
WebSocket Chat — Real-time bidirectional chat with tool approval.

This is the closest to how Claude works in a browser: a WebSocket connection
carries both streaming responses and tool approval requests/responses in
real time, without polling.

Protocol (JSON messages over WebSocket):

    Client → Server:
        {"type": "message", "text": "...", "session_id": "..."}
        {"type": "approve", "approval_id": "...", "approved": true}
        {"type": "interrupt", "session_id": "..."}
        {"type": "set_model", "session_id": "...", "model": "haiku"}
        {"type": "set_reasoning", "session_id": "...", "mode": "native", "budget_tokens": 8000}

    Server → Client:
        {"type": "start"}
        {"type": "text-delta", "delta": "..."}
        {"type": "tool-input-available", "toolName": "...", "input": {...}}
        {"type": "tool-output-available", "toolName": "...", "output": "..."}
        {"type": "approval-needed", "id": "...", "tool_name": "...", "args": {...}}
        {"type": "finish", "finishReason": "..."}
        {"type": "error", "error": "..."}
        {"type": "interrupted", "session_id": "..."}
        {"type": "reasoning-start", "id": "..."}
        {"type": "reasoning-delta", "id": "...", "delta": "..."}
        {"type": "reasoning-end", "id": "..."}

Usage:
    uvicorn examples.api.websocket_chat:app --reload --port 8005

    # Connect with websocat, wscat, or a browser WebSocket client:
    websocat ws://localhost:8005/ws
    > {"type": "message", "text": "Hello!", "session_id": "user-1"}
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

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
logger = logging.getLogger("ws-chat")

# ============================================================================
# Custom tools
# ============================================================================


def web_search(query: str, max_results: int = 5) -> dict:
    """Search the web for information."""
    return {
        "query": query,
        "results": [
            {"title": f"Result {i+1}: {query}", "url": f"https://example.com/{i+1}"}
            for i in range(min(max_results, 5))
        ],
    }


def calculator(expression: str) -> dict:
    """Evaluate a math expression."""
    allowed = set("0123456789+-*/.() ")
    if not all(c in allowed for c in expression):
        return {"error": "Invalid characters"}
    try:
        return {"result": eval(expression, {"__builtins__": {}})}  # noqa: S307
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# Harness
# ============================================================================

skills_dir = Path(__file__).parent.parent / "skills"

harness = VelHarness(
    model={
        "provider": "anthropic",
        "model": "claude-sonnet-4-5-20250929",
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
    },
    tools=[web_search, calculator],
    skill_dirs=[str(skills_dir)] if skills_dir.exists() else [],
    sandbox=True,
    planning=True,
    memory=True,
    caching=True,
    retry=True,
    fallback_model="haiku",
    max_fallback_retries=1,
    working_directory=str(Path(__file__).parent.parent.parent),
)

harness.register_agent(
    "summarizer",
    AgentDefinition(
        description="Summarization agent",
        prompt="Summarize concisely using bullet points.",
        tools=["read_file", "glob", "grep"],
        model="haiku",
        max_turns=15,
    ),
)


# ============================================================================
# Connection & session management
# ============================================================================

sessions: Dict[str, HarnessSession] = {}
# Map WebSocket → set of session_ids so we can push approval notifications
ws_sessions: Dict[WebSocket, set] = {}


def get_or_create_session(session_id: str) -> HarnessSession:
    if session_id not in sessions:
        sessions[session_id] = harness.create_session(session_id=session_id)
    return sessions[session_id]


# ============================================================================
# App
# ============================================================================

app = FastAPI(title="vel-harness WebSocket Chat")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# Minimal HTML test client
TEST_CLIENT_HTML = """
<!DOCTYPE html>
<html>
<head><title>vel-harness WS Chat</title></head>
<body>
<h2>vel-harness WebSocket Chat</h2>
<div id="log" style="height:400px;overflow:auto;border:1px solid #ccc;padding:8px;font-family:monospace;font-size:13px;white-space:pre-wrap;"></div>
<input id="input" style="width:80%;padding:8px;" placeholder="Type a message..." autofocus />
<button onclick="send()">Send</button>
<script>
const ws = new WebSocket(`ws://${location.host}/ws`);
const log = document.getElementById('log');
const input = document.getElementById('input');
ws.onmessage = e => { log.textContent += e.data + '\\n'; log.scrollTop = log.scrollHeight; };
ws.onclose = () => { log.textContent += '[disconnected]\\n'; };
function send() {
  const text = input.value.trim();
  if (!text) return;
  const msg = JSON.stringify({type:'message', text, session_id:'browser'});
  ws.send(msg);
  log.textContent += '> ' + text + '\\n';
  input.value = '';
}
input.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
</script>
</body>
</html>
"""


@app.get("/")
async def index():
    return HTMLResponse(TEST_CLIENT_HTML)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_sessions[ws] = set()
    logger.info("WebSocket connected")

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "error": "Invalid JSON"})
                continue

            msg_type = msg.get("type")

            if msg_type == "message":
                await handle_message(ws, msg)

            elif msg_type == "approve":
                approval_id = msg.get("approval_id", "")
                approved = msg.get("approved", False)
                harness.approval_manager.respond(approval_id, approved=approved)
                await ws.send_json({"type": "approval-resolved", "id": approval_id, "approved": approved})

            elif msg_type == "interrupt":
                sid = msg.get("session_id", "default")
                if sid in sessions:
                    sessions[sid].interrupt()
                    await ws.send_json({"type": "interrupted", "session_id": sid})

            elif msg_type == "set_model":
                sid = msg.get("session_id", "default")
                session = get_or_create_session(sid)
                session.set_model(msg.get("model", "sonnet"))
                await ws.send_json({"type": "model-changed", "model": session.model})

            elif msg_type == "set_reasoning":
                sid = msg.get("session_id", "default")
                session = get_or_create_session(sid)
                config = {"mode": msg.get("mode", "none")}
                if "budget_tokens" in msg:
                    config["budget_tokens"] = msg["budget_tokens"]
                session.set_reasoning(ReasoningConfig.from_value(config))
                await ws.send_json({"type": "reasoning-changed", "config": config})

            else:
                await ws.send_json({"type": "error", "error": f"Unknown message type: {msg_type}"})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    finally:
        ws_sessions.pop(ws, None)


async def handle_message(ws: WebSocket, msg: Dict[str, Any]):
    """Stream the agent's response over the WebSocket."""
    text = msg.get("text", "")
    session_id = msg.get("session_id", "default")
    session = get_or_create_session(session_id)
    ws_sessions[ws].add(session_id)

    try:
        async for event in session.query(text):
            await ws.send_json(event)
    except Exception as e:
        logger.exception("Error during query")
        await ws.send_json({"type": "error", "error": str(e)})
