"""
Filesystem tool prompts - read, write, edit, ls, glob, grep.
Source: Piebald claude-code-system-prompts (adapted)
"""

READ_TOOL_PROMPT = """
# Read Tool Guidelines

Reads a file from the local filesystem. You can access any file directly by using this tool.
Assume this tool is able to read all files on the machine. If the User provides a path to a file assume that path is valid. It is okay to read a file that does not exist; an error will be returned.

## Usage

- The file_path parameter must be an absolute path, not a relative path
- By default, it reads up to 2000 lines starting from the beginning of the file
- You can optionally specify a line offset and limit (especially handy for long files), but it's recommended to read the whole file by not providing these parameters
- Any lines longer than 2000 characters will be truncated
- Results are returned using cat -n format, with line numbers starting at 1
- This tool can read images (PNG, JPG, etc). When reading an image file the contents are presented visually.
- This tool can read PDF files (.pdf). PDFs are processed page by page, extracting both text and visual content for analysis.
- This tool can read Jupyter notebooks (.ipynb files) and returns all cells with their outputs, combining code, text, and visualizations.
- This tool can only read files, not directories. To read a directory, use the `ls` tool or an ls command via the `execute` tool.
- You can call multiple tools in a single response. It is always better to speculatively read multiple potentially useful files in parallel.
- You will regularly be asked to read screenshots. If the user provides a path to a screenshot, ALWAYS use this tool to view the file at the path. This tool will work with all temporary file paths.
- If you read a file that exists but has empty contents you will receive a system reminder warning in place of file contents.
"""

WRITE_TOOL_PROMPT = """
# Write Tool Guidelines

The `write_file` tool creates or overwrites files.

## Usage

- This tool will overwrite existing files at the provided path
- If the file exists, you MUST read it first before writing
- ALWAYS prefer editing existing files over creating new ones
- NEVER proactively create documentation files (*.md) or README files unless explicitly requested

## Restrictions

- Only use emojis in files if the user explicitly requests it
- Never write new files unless explicitly required
"""

EDIT_TOOL_PROMPT = """
# Edit Tool Guidelines

The `edit_file` tool performs exact string replacements in files.

## Usage

- You MUST read the file first before editing
- Preserve exact indentation (tabs/spaces) when specifying old_string
- The edit will FAIL if `old_string` is not unique - provide more context to make it unique
- Use `replace_all` for renaming variables or replacing all occurrences

## Best Practices

- ALWAYS prefer editing existing files over writing new ones
- Only use emojis if the user explicitly requests it
- Provide sufficient context in old_string to ensure uniqueness
"""

LS_TOOL_PROMPT = """
# List Directory Guidelines

The `ls` tool lists directory contents.

## Usage

- Provide a path to list its contents
- Returns files and directories at that location
- Use for exploring directory structure
- Prefer `glob` for pattern-based file finding
"""

GLOB_TOOL_PROMPT = """
# Glob Tool Guidelines

The `glob` tool finds files by pattern matching.

## Usage

- Fast file pattern matching that works with any codebase size
- Supports patterns like "**/*.js" or "src/**/*.ts"
- Returns matching file paths sorted by modification time
- Use when you need to find files by name patterns

## Best Practices

- Prefer over bash `find` command for file discovery
- Can speculatively run multiple searches in parallel
- For open-ended searches requiring multiple rounds, consider using the task/agent tool
"""

GREP_TOOL_PROMPT = """
# Grep Tool Guidelines

The `grep` tool searches file contents using ripgrep.

## Usage

- ALWAYS use `grep` for content search. NEVER invoke `grep` or `rg` as a bash command.
- Supports full regex syntax (e.g., "log.*Error", "function\\s+\\w+")
- Filter files with glob parameter (e.g., "*.js", "**/*.tsx") or type parameter

## Output Modes

- "content": Shows matching lines
- "files_with_matches": Shows only file paths (default)
- "count": Shows match counts

## Pattern Syntax

- Uses ripgrep (not grep) - literal braces need escaping
- Use `interface\\{\\}` to find `interface{}` in Go code
- For cross-line patterns, use `multiline: true`

## Best Practices

- Use for finding code patterns, function definitions, imports
- For open-ended searches requiring multiple rounds, consider using the task/agent tool
"""

# Token count estimates
TOKEN_ESTIMATE = 700  # Combined for all filesystem tools
