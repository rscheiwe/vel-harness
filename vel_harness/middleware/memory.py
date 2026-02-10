"""
Memory Middleware

Implements memory-first protocol for persistent knowledge across sessions.
- Loads AGENTS.md at startup
- Instructs agent to check /memories/ before responding
- Provides tools for memory management
"""

from typing import Any, Callable, Dict, List, Optional, Protocol

from vel import ToolSpec


class FilesystemBackend(Protocol):
    """Protocol for filesystem backends."""

    def read_file(self, path: str, offset: int = 0, limit: int = 100) -> Dict[str, Any]: ...
    def write_file(self, path: str, content: str) -> Dict[str, Any]: ...
    def exists(self, path: str) -> bool: ...
    def ls(self, path: str) -> Dict[str, Any]: ...
    def glob(self, pattern: str) -> Dict[str, Any]: ...


class MemoryMiddleware:
    """
    Middleware that implements memory-first protocol.

    - Loads AGENTS.md at startup
    - Instructs agent to check /memories/ before responding
    - Provides tools for memory management
    """

    def __init__(
        self,
        memories_path: str = "/memories/",
        agents_md_path: str = "/memories/AGENTS.md",
    ):
        self.memories_path = memories_path
        self.agents_md_path = agents_md_path
        self._filesystem: Optional[FilesystemBackend] = None

    def set_filesystem(self, filesystem: FilesystemBackend) -> None:
        """Set the filesystem backend."""
        self._filesystem = filesystem

    def get_startup_context(self, filesystem_backend: Optional[FilesystemBackend] = None) -> str:
        """Load AGENTS.md if it exists."""
        backend = filesystem_backend or self._filesystem
        if not backend:
            return ""

        if not backend.exists(self.agents_md_path):
            return ""

        result = backend.read_file(self.agents_md_path)
        if "error" in result:
            return ""

        content = result.get("content", "")
        # Strip line numbers if present
        lines = []
        for line in content.split("\n"):
            if " | " in line:
                lines.append(line.split(" | ", 1)[1])
            else:
                lines.append(line)
        content = "\n".join(lines)

        if content:
            return f"<agent_memory>\n{content}\n</agent_memory>"
        return ""

    def get_system_prompt_segment(self) -> str:
        """System prompt for memory-first protocol."""
        return f"""
## Long-term Memory

You have persistent memory in `{self.memories_path}`:

**Memory-First Protocol:**
1. **Before research**: Check {self.memories_path} for relevant prior knowledge
2. **During work**: Reference memory files when uncertain
3. **After learning**: Save new information to {self.memories_path}

**Memory Organization:**
- `{self.agents_md_path}` - Your core knowledge (always loaded at startup)
- `{self.memories_path}api-conventions.md` - API patterns
- `{self.memories_path}project-notes.md` - Project-specific info
- Organize by topic with descriptive filenames

**When to save to memory:**
- User teaches you something they want remembered
- You discover project-specific patterns
- Important decisions are made

Files in {self.memories_path} persist across sessions.
"""

    def get_tools(self) -> List[ToolSpec]:
        """Get memory management tools."""
        middleware = self

        def list_memories() -> Dict[str, Any]:
            """
            List all files in long-term memory.

            Returns:
                List of memory files with their paths
            """
            if not middleware._filesystem:
                return {"error": "Filesystem not configured"}

            result = middleware._filesystem.ls(middleware.memories_path)
            entries = result.get("entries", [])

            # Recursively list subdirectories
            all_files: List[Dict[str, Any]] = []

            def collect_files(path: str) -> None:
                ls_result = middleware._filesystem.ls(path)
                for entry in ls_result.get("entries", []):
                    if entry["type"] == "file":
                        all_files.append({
                            "path": entry["path"],
                            "name": entry["name"],
                        })
                    elif entry["type"] == "directory":
                        collect_files(entry["path"])

            collect_files(middleware.memories_path)

            return {
                "memories_path": middleware.memories_path,
                "files": all_files,
                "count": len(all_files),
            }

        def save_memory(
            filename: str,
            content: str,
            category: str = "",
        ) -> Dict[str, Any]:
            """
            Save information to long-term memory.

            Args:
                filename: Name for the memory file (e.g., 'api-patterns.md')
                content: Content to save
                category: Optional subdirectory (e.g., 'projects', 'apis')

            Returns:
                Confirmation of save
            """
            if not middleware._filesystem:
                return {"error": "Filesystem not configured"}

            # Build path
            if category:
                path = f"{middleware.memories_path}{category}/{filename}"
            else:
                path = f"{middleware.memories_path}{filename}"

            result = middleware._filesystem.write_file(path, content)

            if "error" in result:
                return result

            return {
                "status": "saved",
                "path": path,
                "note": "This memory will persist across sessions",
            }

        def recall_memory(path: str) -> Dict[str, Any]:
            """
            Recall information from long-term memory.

            Args:
                path: Path to the memory file (e.g., '/memories/api-patterns.md')

            Returns:
                Contents of the memory file
            """
            if not middleware._filesystem:
                return {"error": "Filesystem not configured"}

            # Ensure path starts with memories_path
            if not path.startswith(middleware.memories_path):
                path = f"{middleware.memories_path}{path.lstrip('/')}"

            result = middleware._filesystem.read_file(path)

            if "error" in result:
                return result

            content = result.get("content", "")
            # Strip line numbers
            lines = []
            for line in content.split("\n"):
                if " | " in line:
                    lines.append(line.split(" | ", 1)[1])
                else:
                    lines.append(line)

            return {
                "path": path,
                "content": "\n".join(lines),
            }

        def search_memories(query: str) -> Dict[str, Any]:
            """
            Search across all memory files.

            Args:
                query: Text or regex pattern to search for

            Returns:
                Matching lines from memory files
            """
            if not middleware._filesystem:
                return {"error": "Filesystem not configured"}

            # Use grep on memories path
            if hasattr(middleware._filesystem, "grep"):
                return middleware._filesystem.grep(query, middleware.memories_path)

            # Fallback: manual search
            matches: List[Dict[str, Any]] = []
            ls_result = middleware._filesystem.ls(middleware.memories_path)

            for entry in ls_result.get("entries", []):
                if entry["type"] == "file":
                    read_result = middleware._filesystem.read_file(entry["path"])
                    if "content" in read_result:
                        content = read_result["content"]
                        for i, line in enumerate(content.split("\n"), 1):
                            if query.lower() in line.lower():
                                matches.append({
                                    "file": entry["path"],
                                    "line": i,
                                    "content": line.strip(),
                                })

            return {
                "query": query,
                "matches": matches[:50],  # Limit results
                "total_matches": len(matches),
            }

        def update_agents_md(content: str) -> Dict[str, Any]:
            """
            Update the AGENTS.md core knowledge file.

            This file is loaded at the start of every session.

            Args:
                content: New content for AGENTS.md

            Returns:
                Confirmation of update
            """
            if not middleware._filesystem:
                return {"error": "Filesystem not configured"}

            result = middleware._filesystem.write_file(
                middleware.agents_md_path,
                content,
            )

            if "error" in result:
                return result

            return {
                "status": "updated",
                "path": middleware.agents_md_path,
                "note": "This will be loaded at the start of every session",
            }

        return [
            ToolSpec.from_function(
                list_memories,
                name="list_memories",
                description="List all files in long-term memory. Use to see what knowledge has been saved.",
                category="memory",
                tags=["memory", "knowledge", "list"],
            ),
            ToolSpec.from_function(
                save_memory,
                name="save_memory",
                description="Save information to long-term memory. Use to persist important knowledge across sessions.",
                category="memory",
                tags=["memory", "knowledge", "save"],
            ),
            ToolSpec.from_function(
                recall_memory,
                name="recall_memory",
                description="Recall information from a specific memory file. Use to retrieve saved knowledge.",
                category="memory",
                tags=["memory", "knowledge", "recall"],
            ),
            ToolSpec.from_function(
                search_memories,
                name="search_memories",
                description="Search across all memory files for matching content. Use to find relevant prior knowledge.",
                category="memory",
                tags=["memory", "knowledge", "search"],
            ),
            ToolSpec.from_function(
                update_agents_md,
                name="update_agents_md",
                description="Update the AGENTS.md core knowledge file. This file is loaded at session start.",
                category="memory",
                tags=["memory", "knowledge", "core"],
            ),
        ]

    def get_state(self) -> Dict[str, Any]:
        """Get serializable state for persistence."""
        return {
            "memories_path": self.memories_path,
            "agents_md_path": self.agents_md_path,
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load state from persistence."""
        if "memories_path" in state:
            self.memories_path = state["memories_path"]
        if "agents_md_path" in state:
            self.agents_md_path = state["agents_md_path"]


def create_memory_middleware(
    memories_path: str = "/memories/",
    agents_md_path: Optional[str] = None,
) -> MemoryMiddleware:
    """
    Create memory middleware.

    Args:
        memories_path: Path prefix for memory storage
        agents_md_path: Path to AGENTS.md (defaults to {memories_path}AGENTS.md)

    Returns:
        Configured MemoryMiddleware
    """
    if agents_md_path is None:
        agents_md_path = f"{memories_path}AGENTS.md"

    return MemoryMiddleware(
        memories_path=memories_path,
        agents_md_path=agents_md_path,
    )
