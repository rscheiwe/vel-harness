#!/usr/bin/env python3
"""
Fetch Piebald-AI Claude Code System Prompts

Downloads prompts from https://github.com/Piebald-AI/claude-code-system-prompts
and saves them to vel_harness/prompts/piebald/

Usage:
    python scripts/fetch_piebald_prompts.py

This script fetches the following prompt files:
- Tool descriptions (bash, readfile, write, edit, glob, grep, todowrite, task, skill)
- Agent prompts (explore, plan, task)
- Main system prompt
- Summarization prompt
"""

import os
import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# GitHub raw content base URL
BASE_URL = "https://raw.githubusercontent.com/Piebald-AI/claude-code-system-prompts/main/system-prompts"

# Prompts to fetch
PROMPTS = [
    # Tool descriptions
    "tool-description-bash.md",
    "tool-description-readfile.md",
    "tool-description-write.md",
    "tool-description-edit.md",
    "tool-description-glob.md",
    "tool-description-grep.md",
    "tool-description-todowrite.md",
    "tool-description-task.md",
    "tool-description-skill.md",

    # Agent prompts
    "agent-prompt-explore.md",
    "agent-prompt-plan-mode-enhanced.md",
    "agent-prompt-task-tool.md",
    "agent-prompt-conversation-summarization.md",

    # Main system prompt (note: CLI-focused, may need adaptation)
    "system-prompt-main-system-prompt.md",
]

# Output directory
SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR.parent / "vel_harness" / "prompts" / "piebald"


def fetch_url(url: str) -> str:
    """Fetch content from URL."""
    request = Request(url)
    request.add_header("User-Agent", "vel-harness/1.0")

    try:
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
    except HTTPError as e:
        if e.code == 404:
            return None
        raise


def main() -> int:
    """Main entry point."""
    print("Fetching Piebald-AI Claude Code System Prompts")
    print(f"Output directory: {OUTPUT_DIR}")
    print()

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    success_count = 0
    error_count = 0
    skip_count = 0

    for prompt_name in PROMPTS:
        url = f"{BASE_URL}/{prompt_name}"
        output_path = OUTPUT_DIR / prompt_name

        print(f"Fetching {prompt_name}...", end=" ")

        try:
            content = fetch_url(url)

            if content is None:
                print("NOT FOUND (skipped)")
                skip_count += 1
                continue

            # Save to file
            output_path.write_text(content, encoding="utf-8")
            print(f"OK ({len(content)} bytes)")
            success_count += 1

        except (URLError, HTTPError) as e:
            print(f"ERROR: {e}")
            error_count += 1

        except Exception as e:
            print(f"ERROR: {e}")
            error_count += 1

    print()
    print(f"Summary: {success_count} fetched, {skip_count} skipped, {error_count} errors")

    if success_count == 0:
        print()
        print("WARNING: No prompts were fetched.")
        print("This could mean:")
        print("  1. The Piebald-AI repository structure has changed")
        print("  2. Network connectivity issues")
        print("  3. The repository is private or removed")
        print()
        print("The harness will fall back to custom prompts.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
