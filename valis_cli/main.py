"""
Valis CLI Entry Point

Command-line interface using Click.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv

# Load .env file from vel-harness root or current directory
_env_paths = [
    Path(__file__).parent.parent / ".env",  # vel-harness/.env
    Path.cwd() / ".env",  # current directory .env
]
for _env_path in _env_paths:
    if _env_path.exists():
        load_dotenv(_env_path)
        break

from valis_cli.config import Config, get_config, init_project


@click.group(invoke_without_command=True)
@click.option(
    "--model", "-m",
    help="Model to use (e.g., claude-sonnet-4-5-20250929)",
)
@click.option(
    "--provider", "-p",
    default="anthropic",
    help="Model provider (anthropic, openai)",
)
@click.option(
    "--project", "-P",
    type=click.Path(exists=True, path_type=Path),
    help="Project directory",
)
@click.option(
    "--no-sandbox",
    is_flag=True,
    help="Disable sandbox mode",
)
@click.option(
    "--compact",
    is_flag=True,
    help="Use compact display mode",
)
@click.option(
    "--show-thinking",
    is_flag=True,
    help="Show model thinking (if available)",
)
@click.option(
    "--select-mode",
    is_flag=True,
    help="Enable text selection (disables mouse interactions)",
)
@click.pass_context
def cli(
    ctx: click.Context,
    model: Optional[str],
    provider: str,
    project: Optional[Path],
    no_sandbox: bool,
    compact: bool,
    show_thinking: bool,
    select_mode: bool,
) -> None:
    """
    Valis CLI - AI-Powered Development Assistant

    Start an interactive chat session with the AI assistant.
    """
    ctx.ensure_object(dict)

    # Get configuration
    config = get_config(project_dir=project)

    # Apply command-line options
    if model:
        config.model.model = model
    if provider:
        config.model.provider = provider
    if no_sandbox:
        config.sandbox_enabled = False
    if compact:
        config.compact_mode = True
    if show_thinking:
        config.show_thinking = True

    ctx.obj["config"] = config
    ctx.obj["select_mode"] = select_mode

    # If no subcommand, run the TUI
    if ctx.invoked_subcommand is None:
        from valis_cli.app import run_app
        run_app(config=config, mouse=not select_mode)


@cli.command()
@click.argument("prompt")
@click.pass_context
def ask(ctx: click.Context, prompt: str) -> None:
    """
    Ask a single question (non-interactive mode).

    Example: valis ask "What is Python?"
    """
    config = ctx.obj.get("config")

    async def run():
        from valis_cli.agent import run_single_turn
        response = await run_single_turn(prompt, config=config)
        click.echo(response)

    asyncio.run(run())


@cli.command()
@click.option(
    "--path", "-p",
    type=click.Path(path_type=Path),
    default=None,
    help="Directory to initialize",
)
def init(path: Optional[Path]) -> None:
    """
    Initialize a new Valis project.

    Creates .valis directory with default configuration.
    """
    try:
        valis_dir = init_project(path)
        click.echo(f"Initialized Valis project at: {valis_dir}")
        click.echo("\nCreated:")
        click.echo("  - .valis/config.json")
        click.echo("  - .valis/memories/")
        click.echo("  - .valis/skills/")
        click.echo("  - .valis/AGENTS.md")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def config(ctx: click.Context) -> None:
    """
    Show current configuration.
    """
    cfg = ctx.obj.get("config")
    if cfg is None:
        cfg = get_config()

    click.echo("Valis CLI Configuration")
    click.echo("=" * 40)
    click.echo(f"Global dir:     {cfg.global_dir}")
    click.echo(f"Project dir:    {cfg.project_dir or 'None'}")
    click.echo(f"Model:          {cfg.model.provider}/{cfg.model.model}")
    click.echo(f"Sandbox:        {cfg.sandbox_enabled}")
    click.echo(f"Compact mode:   {cfg.compact_mode}")
    click.echo(f"Show thinking:  {cfg.show_thinking}")
    click.echo(f"Show tools:     {cfg.show_tool_calls}")


@cli.command()
@click.pass_context
def skills(ctx: click.Context) -> None:
    """
    List available skills.
    """
    cfg = ctx.obj.get("config")
    if cfg is None:
        cfg = get_config()

    click.echo("Available Skills")
    click.echo("=" * 40)

    found = False

    # Check global skills
    if cfg.skills_dir.exists():
        for path in sorted(cfg.skills_dir.iterdir()):
            if path.suffix in (".py", ".yaml", ".yml", ".md"):
                click.echo(f"  [global] {path.stem}")
                found = True

    # Check project skills
    if cfg.project_dir:
        project_skills = cfg.project_dir / "skills"
        if project_skills.exists():
            for path in sorted(project_skills.iterdir()):
                if path.suffix in (".py", ".yaml", ".yml", ".md"):
                    click.echo(f"  [project] {path.stem}")
                    found = True

    if not found:
        click.echo("  No skills found")


@cli.command()
@click.option(
    "--provider", "-p",
    help="Filter by provider",
)
def models(provider: Optional[str]) -> None:
    """
    List available models.
    """
    # Common models by provider
    model_list = {
        "anthropic": [
            "claude-sonnet-4-5-20250929",
            "claude-opus-4-5-20251101",
            "claude-3-5-haiku-20241022",
        ],
        "openai": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
        ],
    }

    click.echo("Available Models")
    click.echo("=" * 40)

    for prov, models in model_list.items():
        if provider and prov != provider:
            continue
        click.echo(f"\n{prov}:")
        for m in models:
            click.echo(f"  - {m}")


@cli.command()
def version() -> None:
    """
    Show version information.
    """
    click.echo("Valis CLI v0.1.0")
    click.echo("Built on vel-harness")


def main() -> None:
    """Main entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
