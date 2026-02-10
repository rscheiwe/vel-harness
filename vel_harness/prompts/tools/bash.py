"""
Bash/execute tool prompt - shell command execution guidance.
Source: Piebald claude-code-system-prompts (adapted)
"""

BASH_TOOL_PROMPT = """
# Bash/Execute Tool Guidelines

The `execute` tool runs bash commands in the user's environment.

## Important Restrictions

This tool is for terminal operations like git, npm, docker, etc. DO NOT use it for file operations (reading, writing, editing, searching, finding files) - use the specialized tools instead:
- File search: Use `glob` (NOT find or ls)
- Content search: Use `grep` (NOT grep or rg command)
- Read files: Use `read_file` (NOT cat/head/tail)
- Edit files: Use `edit_file` (NOT sed/awk)
- Write files: Use `write_file` (NOT echo >/cat <<EOF)

## Pre-Execution Steps

1. **Directory Verification**: Before creating files/directories, verify the parent exists using `ls`
2. **Quote Paths**: Always quote file paths containing spaces with double quotes

## Execution Behavior

- Working directory persists between commands; shell state does not
- Shell environment initialized from user's profile (bash or zsh)
- Output may be truncated if it exceeds limits; use file redirection for full output

## Command Chaining

- Independent commands: Make parallel tool calls
- Dependent commands: Chain with `&&` in a single call
- When order matters but failures don't: Use `;`
- DO NOT use newlines to separate commands

## Best Practices

- Maintain current working directory using absolute paths; avoid `cd` unless explicitly requested
- Prefer explicit file paths over glob patterns for destructive operations
- For long-running processes, consider background execution

## Security

- Avoid commands modifying system configuration without approval
- Never execute commands exposing sensitive credentials
- Be cautious with ~/.ssh, ~/.aws, or other credential paths

## Avoid Without Approval

- `rm -rf` - Destructive operations
- `chmod 777` - Overly permissive permissions
- Commands involving credential paths
"""

# Token count estimate
TOKEN_ESTIMATE = 400
