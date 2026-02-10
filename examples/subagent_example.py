#!/usr/bin/env python3
"""
VelHarness Subagent Example

Demonstrates using typed subagents (explore, plan, default) for
parallel and specialized task execution.

Usage:
    python examples/subagent_example.py

Requirements:
    - .env file with ANTHROPIC_API_KEY or environment variable
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent to path for development
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env file
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from vel_harness import VelHarness, AgentConfig


async def main():
    # Check API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    skills_dir = Path(__file__).parent / "skills"

    print("=" * 60)
    print("VelHarness Subagent Example")
    print("=" * 60)

    # Create harness
    harness = VelHarness(
        model={
            "provider": "anthropic",
            "model": "claude-sonnet-4-5-20250929",
        },
        skill_dirs=[str(skills_dir)],
        sandbox=True,
        planning=True,
    )

    # Show available agent types
    print("\nAvailable agent types:")
    for agent_type in harness.list_agent_types():
        config = harness.agent_registry.get(agent_type)
        print(f"  - {agent_type}: {config.description}")
    print()

    # Example 1: Explore agent (read-only)
    print("-" * 40)
    print("Example 1: Explore Agent")
    print("-" * 40)
    print("Using explore agent to investigate the skills directory...\n")

    result = await harness.run(
        f"Use an explore agent to look at the files in {skills_dir} and "
        "describe what skills are available. The agent should only read, not modify.",
        session_id="subagent-demo"
    )
    print(f"Result:\n{result}\n")

    # Example 2: Plan agent
    print("-" * 40)
    print("Example 2: Plan Agent")
    print("-" * 40)
    print("Using plan agent to create a structured plan...\n")

    result = await harness.run(
        "Use a plan agent to create a step-by-step plan for implementing "
        "a user authentication system. The plan should be structured with clear phases.",
        session_id="subagent-demo"
    )
    print(f"Result:\n{result}\n")

    # Example 3: Register custom agent
    print("-" * 40)
    print("Example 3: Custom Agent Registration")
    print("-" * 40)

    harness.register_agent(
        "code-reviewer",
        AgentConfig(
            name="code-reviewer",
            system_prompt="""You are a code review specialist. When given code:
1. Identify potential bugs
2. Suggest improvements
3. Rate code quality 1-10
Always be constructive and specific.""",
            tools=["read_file", "grep", "glob"],
            max_turns=20,
            description="Specialized agent for code review tasks",
        )
    )

    print("Registered custom 'code-reviewer' agent")
    print(f"Available agents: {harness.list_agent_types()}\n")

    # Example 4: Multiple parallel subagents (conceptual)
    print("-" * 40)
    print("Example 4: Parallel Research Pattern")
    print("-" * 40)
    print("Demonstrating parallel subagent spawning pattern...\n")

    result = await harness.run(
        """I need to research a topic from multiple angles.

Spawn THREE explore agents in parallel to investigate:
1. First agent: Find all Python files in the skills directory
2. Second agent: Search for the word "trigger" in skill files
3. Third agent: List the structure of the examples directory

After all complete, synthesize the findings into a summary.""",
        session_id="parallel-demo"
    )
    print(f"Result:\n{result}\n")

    print("=" * 60)
    print("Subagent examples complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
