#!/usr/bin/env python3
"""
VelHarness Streaming Example

Demonstrates streaming responses with the Vercel AI SDK V5 protocol.
Shows how to handle different event types.

Usage:
    python examples/streaming_example.py

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


async def handle_stream_events(harness: VelHarness, prompt: str, session_id: str = "stream-demo"):
    """Process streaming events and display them nicely."""
    print(f"\n{'='*60}")
    print(f"Prompt: {prompt}")
    print(f"{'='*60}\n")

    current_text = []
    tool_calls = []

    async for event in harness.run_stream(prompt, session_id=session_id):
        event_type = event.get("type", "unknown")

        if event_type == "start":
            print("[Stream started]")

        elif event_type == "text-delta":
            # Streaming text content
            delta = event.get("delta", "")
            print(delta, end="", flush=True)
            current_text.append(delta)

        elif event_type == "text-end":
            print()  # Newline after text

        elif event_type == "tool-input-available":
            # Tool is about to be called
            tool_name = event.get("toolName", "unknown")
            tool_input = event.get("input", {})
            print(f"\n[Tool Call: {tool_name}]")
            print(f"  Input: {str(tool_input)[:100]}...")
            tool_calls.append({"name": tool_name, "input": tool_input})

        elif event_type == "tool-output-available":
            # Tool has returned
            tool_name = event.get("toolName", "unknown")
            output = event.get("output", "")
            output_preview = str(output)[:200] + "..." if len(str(output)) > 200 else str(output)
            print(f"[Tool Result: {tool_name}]")
            print(f"  Output: {output_preview}")

        elif event_type == "finish":
            print("\n[Stream finished]")
            finish_reason = event.get("finishReason", "unknown")
            print(f"  Reason: {finish_reason}")

        elif event_type == "error":
            error = event.get("error", "Unknown error")
            print(f"\n[Error]: {error}")

    # Summary
    print(f"\n{'='*60}")
    print("Summary:")
    print(f"  Text length: {len(''.join(current_text))} chars")
    print(f"  Tool calls: {len(tool_calls)}")
    for tc in tool_calls:
        print(f"    - {tc['name']}")
    print(f"{'='*60}")


async def main():
    # Check API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    skills_dir = Path(__file__).parent / "skills"

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

    print("VelHarness Streaming Demo")
    print("=" * 60)
    print("This demo shows streaming events from the harness.")
    print()

    # Demo 1: Simple streaming text
    print("\n[Demo 1: Simple Text Response]")
    await handle_stream_events(
        harness,
        "Explain what streaming is in 2-3 sentences.",
        session_id="stream-demo-1"
    )

    # Demo 2: With tool use
    print("\n[Demo 2: Tool Use (bash)]")
    await handle_stream_events(
        harness,
        "Run 'echo Hello from streaming!' and tell me the output.",
        session_id="stream-demo-2"
    )

    # Demo 3: Skill loading
    print("\n[Demo 3: Skill Loading]")
    await handle_stream_events(
        harness,
        "Load the Test Skill and follow its instructions.",
        session_id="stream-demo-3"
    )

    print("\n\nStreaming demo complete!")


if __name__ == "__main__":
    asyncio.run(main())
