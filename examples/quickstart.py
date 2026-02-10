#!/usr/bin/env python3
"""
VelHarness Quickstart Example

This example demonstrates basic usage of the VelHarness API.
No API server needed - just run this script directly.

Usage:
    python examples/quickstart.py

Requirements:
    - .env file with ANTHROPIC_API_KEY or environment variable
    - vel package installed (pip install vel)
"""

import asyncio
import os
from pathlib import Path

# Add parent to path for development
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env file
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from vel_harness import VelHarness


async def main():
    # Ensure API key is set
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not found")
        print("Either create a .env file or set the environment variable")
        return

    # Get the skills directory relative to this file
    skills_dir = Path(__file__).parent / "skills"

    print("=" * 60)
    print("VelHarness Quickstart Example")
    print("=" * 60)
    print(f"Skills directory: {skills_dir}")
    print()

    # Create the harness
    harness = VelHarness(
        model={
            "provider": "anthropic",
            "model": "claude-sonnet-4-5-20250929",
        },
        skill_dirs=[str(skills_dir)],
        sandbox=True,  # Enable bash execution
        planning=True,  # Enable todo tools
    )

    print("Available agent types:", harness.list_agent_types())
    print()

    # Example 1: Simple question
    print("-" * 40)
    print("Example 1: Simple response")
    print("-" * 40)

    result = await harness.run(
        "What is 2 + 2? Reply with just the number.",
        session_id="quickstart-session",
    )
    print(f"Response: {result}")
    print()

    # Example 2: File listing (uses tools)
    print("-" * 40)
    print("Example 2: List files (uses ls tool)")
    print("-" * 40)

    examples_dir = Path(__file__).parent
    result = await harness.run(
        f"List the files in {examples_dir}. Just show the filenames.",
        session_id="quickstart-session",
    )
    print(f"Response: {result}")
    print()

    # Example 3: Skill loading
    print("-" * 40)
    print("Example 3: Load a skill")
    print("-" * 40)

    result = await harness.run(
        "Load the 'Test Skill' and follow its verification instructions.",
        session_id="quickstart-session",
    )
    print(f"Response: {result}")
    print()

    print("=" * 60)
    print("Quickstart complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
