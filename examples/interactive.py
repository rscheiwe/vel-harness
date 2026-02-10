#!/usr/bin/env python3
"""
VelHarness Interactive REPL

A simple interactive session for testing the harness manually.
Type messages and see responses with tool use.

Usage:
    python examples/interactive.py

Commands:
    /quit or /exit - Exit the session
    /reset - Clear session and start fresh
    /skills - List available skills
    /agents - List available agent types

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

from vel_harness import VelHarness


async def interactive_session():
    """Run an interactive session with the harness."""
    # Check API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    skills_dir = Path(__file__).parent / "skills"
    session_id = "interactive"

    print("=" * 60)
    print("VelHarness Interactive Session")
    print("=" * 60)
    print()
    print("Commands:")
    print("  /quit, /exit  - Exit")
    print("  /reset        - Clear session")
    print("  /skills       - List skills")
    print("  /agents       - List agent types")
    print("  /stream       - Toggle streaming mode")
    print()

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

    streaming = False
    print(f"Skills loaded from: {skills_dir}")
    print(f"Agent types: {', '.join(harness.list_agent_types())}")
    print()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        # Handle commands
        if user_input.lower() in ["/quit", "/exit"]:
            print("Goodbye!")
            break

        elif user_input.lower() == "/reset":
            session_id = f"interactive-{id(harness)}"
            print("Session reset.")
            continue

        elif user_input.lower() == "/skills":
            skills = harness.deep_agent.skills
            if skills:
                result = skills._list_skills()
                print(f"\nAvailable skills ({result['total']}):")
                for s in result["skills"]:
                    active = " [ACTIVE]" if s["active"] else ""
                    print(f"  - {s['name']}: {s['description']}{active}")
            else:
                print("Skills middleware not enabled")
            print()
            continue

        elif user_input.lower() == "/agents":
            print("\nAvailable agent types:")
            for agent_type in harness.list_agent_types():
                config = harness.agent_registry.get(agent_type)
                print(f"  - {agent_type}: {config.description}")
            print()
            continue

        elif user_input.lower() == "/stream":
            streaming = not streaming
            print(f"Streaming mode: {'ON' if streaming else 'OFF'}")
            continue

        # Run the prompt
        print("\nAssistant: ", end="", flush=True)

        try:
            if streaming:
                async for event in harness.run_stream(user_input, session_id=session_id):
                    event_type = event.get("type", "")
                    if event_type == "text-delta":
                        print(event.get("delta", ""), end="", flush=True)
                    elif event_type == "tool-input-available":
                        tool_name = event.get("toolName", "unknown")
                        print(f"\n  [Using {tool_name}...]", end="", flush=True)
                    elif event_type == "tool-output-available":
                        print(" done", end="", flush=True)
                print()  # Newline after streaming
            else:
                result = await harness.run(user_input, session_id=session_id)
                print(result)

        except Exception as e:
            print(f"\nError: {e}")

        print()


def main():
    asyncio.run(interactive_session())


if __name__ == "__main__":
    main()
