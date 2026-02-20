#!/usr/bin/env python3
"""
Skills & Subagents.

Shows:
- Loading skill directories (YAML frontmatter .md files)
- Listing / activating / deactivating skills
- Registering custom agent types (AgentDefinition)
- Listing agent types
- Chat where the agent can spawn subagents

Usage:
    uvicorn examples.api.skills_and_subagents:app --reload --port 8003

    # List loaded skills
    curl http://localhost:8003/skills

    # List agent types (default + custom)
    curl http://localhost:8003/agents

    # Chat — agent can use skills and spawn subagents
    curl -N -X POST http://localhost:8003/chat \
      -H "Content-Type: application/json" \
      -d '{"message": "Research the project structure then write a summary"}'

    # Add a new custom skill at runtime
    curl -X POST http://localhost:8003/skills \
      -H "Content-Type: application/json" \
      -d '{"name": "SQL Expert", "description": "SQL query guidelines", "content": "Always use parameterized queries...", "triggers": ["sql", "query", "database"], "tags": ["database"]}'
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from vel_harness import AgentDefinition, VelHarness

app = FastAPI(title="vel-harness Skills & Subagents")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

skills_dir = Path(__file__).parent.parent / "skills"

harness = VelHarness(
    model={
        "provider": "anthropic",
        "model": "claude-sonnet-4-5-20250929",
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
    },
    skill_dirs=[str(skills_dir)],
    sandbox=True,
    planning=True,
    working_directory=str(Path(__file__).parent.parent.parent),
)

# ---------------------------------------------------------------------------
# Register custom agent types beyond the built-in default/explore/plan
# ---------------------------------------------------------------------------

harness.register_agent(
    "code-reviewer",
    AgentDefinition(
        description="Reviews code for quality, security, and best practices",
        prompt="You are a senior code reviewer. Analyze code for bugs, security issues, "
        "performance problems, and style violations. Be specific and actionable.",
        tools=["read_file", "glob", "grep"],
        model="sonnet",
        max_turns=20,
        timeout=120.0,
    ),
)

harness.register_agent(
    "researcher",
    AgentDefinition(
        description="Deep research agent that gathers and synthesizes information",
        prompt="You are a thorough researcher. Explore the codebase, read documentation, "
        "and provide comprehensive answers backed by evidence from the source code.",
        tools=["read_file", "ls", "glob", "grep"],
        model="haiku",
        max_turns=30,
        timeout=180.0,
    ),
)

harness.register_agent(
    "writer",
    AgentDefinition(
        description="Technical writing agent for documentation and reports",
        prompt="You are a technical writer. Produce clear, well-structured documentation "
        "based on the information provided. Use markdown formatting.",
        tools=["read_file", "write_file", "edit_file", "glob"],
        model="sonnet",
        max_turns=15,
        timeout=120.0,
    ),
)


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class SkillCreateRequest(BaseModel):
    name: str
    description: str
    content: str
    triggers: List[str] = []
    tags: List[str] = []
    priority: int = 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/chat")
async def chat_stream(req: ChatRequest):
    """Chat with skills and subagents available.

    The agent sees all loaded skills and can activate them. It can also
    spawn subagents (default, explore, plan, code-reviewer, researcher, writer)
    to delegate subtasks.
    """

    async def event_generator():
        async for event in harness.run_stream(req.message, session_id=req.session_id):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/skills")
async def list_skills():
    """List all loaded skills with metadata."""
    registry = harness.deep_agent.skills
    if registry is None:
        return {"skills": [], "message": "Skills middleware not enabled"}
    all_skills = registry.list_all()
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
            for s in all_skills
        ],
        "total": len(all_skills),
    }


@app.post("/skills")
async def add_skill(req: SkillCreateRequest):
    """Register a new skill at runtime (no .md file needed)."""
    from vel_harness import Skill

    registry = harness.deep_agent.skills
    if registry is None:
        raise HTTPException(400, "Skills middleware not enabled")

    skill = Skill(
        name=req.name,
        description=req.description,
        content=req.content,
        triggers=req.triggers,
        tags=req.tags,
        priority=req.priority,
        enabled=True,
    )
    registry.register(skill)
    return {"registered": req.name}


@app.get("/agents")
async def list_agents():
    """List all registered agent types (built-in + custom)."""
    registry = harness.agent_registry
    all_agents = registry.get_all()
    return {
        "agents": {
            agent_id: {
                "description": config.description,
                "tools": config.tools,
                "max_turns": config.max_turns,
                "model": config.model,
            }
            for agent_id, config in all_agents.items()
        },
    }


@app.post("/agents/{agent_id}")
async def register_agent(agent_id: str, definition: Dict):
    """Register a new agent type at runtime."""
    harness.register_agent(agent_id, AgentDefinition.from_dict(definition))
    return {"registered": agent_id}
