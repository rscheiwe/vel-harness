"""
Piebald AI Claude Code System Prompts

Vendored prompts from Piebald-AI/claude-code-system-prompts.
These are the actual prompts used by Claude Code.

See: https://github.com/Piebald-AI/claude-code-system-prompts

To update these prompts, run:
    python scripts/fetch_piebald_prompts.py
"""

from pathlib import Path

PIEBALD_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    """
    Load a prompt file by name.

    Args:
        name: Prompt filename without extension (e.g., "agent-prompt-explore")

    Returns:
        Prompt content as string

    Raises:
        FileNotFoundError: If prompt file doesn't exist
    """
    path = PIEBALD_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt '{name}' not found. Run 'python scripts/fetch_piebald_prompts.py' to download."
        )
    return path.read_text(encoding="utf-8")


def list_prompts() -> list[str]:
    """List all available Piebald prompts."""
    return [p.stem for p in PIEBALD_DIR.glob("*.md")]


def has_prompts() -> bool:
    """Check if Piebald prompts have been downloaded."""
    return len(list(PIEBALD_DIR.glob("*.md"))) > 0


# Prompt names for easy reference
EXPLORE_PROMPT = "agent-prompt-explore"
PLAN_PROMPT = "agent-prompt-plan-mode-enhanced"
TASK_PROMPT = "agent-prompt-task-tool"
SUMMARIZATION_PROMPT = "agent-prompt-conversation-summarization"
MAIN_SYSTEM_PROMPT = "system-prompt-main-system-prompt"

# Tool description names
TOOL_BASH = "tool-description-bash"
TOOL_READ = "tool-description-readfile"
TOOL_WRITE = "tool-description-write"
TOOL_EDIT = "tool-description-edit"
TOOL_GLOB = "tool-description-glob"
TOOL_GREP = "tool-description-grep"
TOOL_TODO = "tool-description-todowrite"
TOOL_TASK = "tool-description-task"
TOOL_SKILL = "tool-description-skill"
