#!/usr/bin/env python3
"""
Basic Chat API — Minimal FastAPI + VelHarness streaming chat.

Shows:
- SSE streaming endpoint (Vercel AI SDK V5 protocol)
- Non-streaming endpoint
- Health check

Usage:
    uvicorn examples.api.basic_chat:app --reload --port 8000

    # Stream a response
    curl -N -X POST http://localhost:8000/chat \
      -H "Content-Type: application/json" \
      -d '{"message": "Hello, what can you do?"}'

    # Non-streaming
    curl -X POST http://localhost:8000/chat/sync \
      -H "Content-Type: application/json" \
      -d '{"message": "What is 2+2?"}'
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from vel_harness import VelHarness

app = FastAPI(title="vel-harness Basic Chat")
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


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    response: str
    session_id: str


@app.get("/health")
async def health():
    return {"status": "ok", "model": harness.model}


@app.post("/chat")
async def chat_stream(req: ChatRequest):
    """SSE streaming chat endpoint. Each line is a JSON event."""

    async def event_generator():
        async for event in harness.run_stream(req.message, session_id=req.session_id):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/chat/sync", response_model=ChatResponse)
async def chat_sync(req: ChatRequest):
    """Non-streaming chat endpoint. Returns the full response."""
    result = await harness.run(req.message, session_id=req.session_id)
    return ChatResponse(response=result, session_id=req.session_id)
