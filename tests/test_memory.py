"""
Tests for Memory Middleware and Composite Backend
"""

import os
import tempfile
import pytest
import shutil
from unittest.mock import MagicMock

from vel_harness.middleware.memory import (
    MemoryMiddleware,
    create_memory_middleware,
)
from vel_harness.backends.composite import (
    CompositeBackend,
    PersistentStoreBackend,
    RouteConfig,
    create_composite_backend,
)
from vel_harness.backends.state import StateFilesystemBackend


class TestPersistentStoreBackend:
    """Test PersistentStoreBackend class."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        path = tempfile.mkdtemp(prefix="vel_test_")
        yield path
        shutil.rmtree(path, ignore_errors=True)

    @pytest.fixture
    def backend(self, temp_dir):
        """Create a test backend."""
        return PersistentStoreBackend(base_path=temp_dir, agent_id="test-agent")

    def test_init(self, temp_dir):
        """Test initialization creates directories."""
        backend = PersistentStoreBackend(base_path=temp_dir, agent_id="test-agent")
        assert os.path.exists(os.path.join(temp_dir, "test-agent"))

    def test_write_and_read_file(self, backend):
        """Test writing and reading files."""
        result = backend.write_file("/memories/test.txt", "Hello, world!")
        assert result["status"] == "ok"
        assert result["path"] == "/memories/test.txt"

        read_result = backend.read_file("/memories/test.txt")
        assert "Hello, world!" in read_result["content"]
        assert read_result["total_lines"] == 1

    def test_write_creates_directories(self, backend):
        """Test writing creates parent directories."""
        result = backend.write_file("/memories/deep/nested/file.txt", "content")
        assert result["status"] == "ok"

        read_result = backend.read_file("/memories/deep/nested/file.txt")
        assert "content" in read_result["content"]

    def test_edit_file(self, backend):
        """Test editing files."""
        backend.write_file("/memories/edit.txt", "hello world")

        result = backend.edit_file("/memories/edit.txt", "world", "universe")
        assert result["status"] == "ok"

        read_result = backend.read_file("/memories/edit.txt")
        assert "universe" in read_result["content"]

    def test_edit_file_not_found(self, backend):
        """Test editing non-existent file."""
        result = backend.edit_file("/memories/missing.txt", "old", "new")
        assert "error" in result

    def test_delete_file(self, backend):
        """Test deleting files."""
        backend.write_file("/memories/delete.txt", "content")
        assert backend.exists("/memories/delete.txt")

        result = backend.delete_file("/memories/delete.txt")
        assert result["status"] == "ok"
        assert not backend.exists("/memories/delete.txt")

    def test_delete_file_not_found(self, backend):
        """Test deleting non-existent file."""
        result = backend.delete_file("/memories/missing.txt")
        assert "error" in result

    def test_exists(self, backend):
        """Test checking file existence."""
        assert not backend.exists("/memories/test.txt")
        backend.write_file("/memories/test.txt", "content")
        assert backend.exists("/memories/test.txt")

    def test_ls_empty(self, backend):
        """Test listing empty directory."""
        result = backend.ls("/memories/")
        assert result["entries"] == []

    def test_ls_with_files(self, backend):
        """Test listing directory with files."""
        backend.write_file("/memories/file1.txt", "content1")
        backend.write_file("/memories/file2.txt", "content2")
        backend.write_file("/memories/subdir/file3.txt", "content3")

        result = backend.ls("/memories/")
        entries = result["entries"]

        names = [e["name"] for e in entries]
        assert "subdir" in names
        assert "file1.txt" in names
        assert "file2.txt" in names

    def test_glob(self, backend):
        """Test glob pattern matching."""
        backend.write_file("/memories/file1.txt", "content1")
        backend.write_file("/memories/file2.md", "content2")
        backend.write_file("/memories/subdir/file3.txt", "content3")

        result = backend.glob("/memories/*.txt")
        assert "/memories/file1.txt" in result["matches"]
        assert "/memories/file2.md" not in result["matches"]

    def test_grep(self, backend):
        """Test grep search."""
        backend.write_file("/memories/file1.txt", "hello world\nfoo bar")
        backend.write_file("/memories/file2.txt", "goodbye world\nhello again")

        result = backend.grep("hello", "/memories/")
        assert result["total_matches"] == 2
        assert len(result["matches"]) == 2


class TestCompositeBackend:
    """Test CompositeBackend class."""

    @pytest.fixture
    def memory_backend(self):
        """Create in-memory backend."""
        return StateFilesystemBackend()

    @pytest.fixture
    def temp_dir(self):
        """Create temp directory for persistent storage."""
        path = tempfile.mkdtemp(prefix="vel_test_")
        yield path
        shutil.rmtree(path, ignore_errors=True)

    @pytest.fixture
    def persistent_backend(self, temp_dir):
        """Create persistent backend."""
        return PersistentStoreBackend(base_path=temp_dir, agent_id="test")

    @pytest.fixture
    def composite(self, memory_backend, persistent_backend):
        """Create composite backend."""
        return CompositeBackend(
            default=memory_backend,
            routes={"/memories/": persistent_backend},
        )

    def test_route_to_default(self, composite, memory_backend):
        """Test routing to default backend."""
        composite.write_file("/workspace/file.txt", "default content")

        # Should be in memory backend
        assert memory_backend.exists("/workspace/file.txt")

    def test_route_to_memories(self, composite, persistent_backend):
        """Test routing to memories backend."""
        composite.write_file("/memories/knowledge.txt", "memory content")

        # Should be in persistent backend
        assert persistent_backend.exists("/memories/knowledge.txt")

    def test_read_from_correct_backend(self, composite):
        """Test reading from routed backend."""
        composite.write_file("/memories/test.txt", "persistent")
        composite.write_file("/workspace/test.txt", "ephemeral")

        mem_result = composite.read_file("/memories/test.txt")
        ws_result = composite.read_file("/workspace/test.txt")

        assert "persistent" in mem_result["content"]
        assert "ephemeral" in ws_result["content"]

    def test_edit_file_routed(self, composite):
        """Test editing routed file."""
        composite.write_file("/memories/edit.txt", "hello world")
        composite.edit_file("/memories/edit.txt", "world", "universe")

        result = composite.read_file("/memories/edit.txt")
        assert "universe" in result["content"]

    def test_delete_file_routed(self, composite):
        """Test deleting routed file."""
        composite.write_file("/memories/delete.txt", "content")
        assert composite.exists("/memories/delete.txt")

        composite.delete_file("/memories/delete.txt")
        assert not composite.exists("/memories/delete.txt")

    def test_get_routes(self, composite):
        """Test getting route information."""
        routes = composite.get_routes()
        assert "/memories/" in routes
        assert routes["/memories/"] == "PersistentStoreBackend"


class TestMemoryMiddleware:
    """Test MemoryMiddleware class."""

    @pytest.fixture
    def filesystem(self):
        """Create a test filesystem."""
        return StateFilesystemBackend()

    @pytest.fixture
    def middleware(self, filesystem):
        """Create middleware with filesystem."""
        mw = MemoryMiddleware()
        mw.set_filesystem(filesystem)
        return mw

    def test_init_default(self):
        """Test default initialization."""
        mw = MemoryMiddleware()
        assert mw.memories_path == "/memories/"
        assert mw.agents_md_path == "/memories/AGENTS.md"

    def test_init_custom(self):
        """Test custom initialization."""
        mw = MemoryMiddleware(
            memories_path="/custom/",
            agents_md_path="/custom/KNOWLEDGE.md",
        )
        assert mw.memories_path == "/custom/"
        assert mw.agents_md_path == "/custom/KNOWLEDGE.md"

    def test_get_startup_context_no_file(self, middleware):
        """Test startup context when AGENTS.md doesn't exist."""
        context = middleware.get_startup_context()
        assert context == ""

    def test_get_startup_context_with_file(self, middleware, filesystem):
        """Test startup context with AGENTS.md."""
        filesystem.write_file(
            "/memories/AGENTS.md",
            "# Agent Knowledge\n\nImportant facts here."
        )

        context = middleware.get_startup_context()
        assert "<agent_memory>" in context
        assert "Agent Knowledge" in context
        assert "</agent_memory>" in context

    def test_get_startup_context_no_filesystem(self):
        """Test startup context without filesystem."""
        mw = MemoryMiddleware()
        context = mw.get_startup_context()
        assert context == ""

    def test_get_system_prompt_segment(self, middleware):
        """Test system prompt generation."""
        prompt = middleware.get_system_prompt_segment()

        assert "Long-term Memory" in prompt
        assert "/memories/" in prompt
        assert "Memory-First Protocol" in prompt
        assert "AGENTS.md" in prompt

    def test_get_tools(self, middleware):
        """Test tool generation."""
        tools = middleware.get_tools()

        tool_names = [t.name for t in tools]
        assert "list_memories" in tool_names
        assert "save_memory" in tool_names
        assert "recall_memory" in tool_names
        assert "search_memories" in tool_names
        assert "update_agents_md" in tool_names

    def test_list_memories_tool(self, middleware, filesystem):
        """Test list_memories tool."""
        filesystem.write_file("/memories/file1.txt", "content1")
        filesystem.write_file("/memories/file2.md", "content2")

        tools = middleware.get_tools()
        list_memories = next(t for t in tools if t.name == "list_memories")

        result = list_memories._handler()
        assert result["count"] == 2
        paths = [f["path"] for f in result["files"]]
        assert "/memories/file1.txt" in paths
        assert "/memories/file2.md" in paths

    def test_save_memory_tool(self, middleware, filesystem):
        """Test save_memory tool."""
        tools = middleware.get_tools()
        save_memory = next(t for t in tools if t.name == "save_memory")

        result = save_memory._handler(
            filename="test.md",
            content="# Test Memory\n\nContent here.",
        )

        assert result["status"] == "saved"
        assert result["path"] == "/memories/test.md"
        assert filesystem.exists("/memories/test.md")

    def test_save_memory_with_category(self, middleware, filesystem):
        """Test save_memory with category."""
        tools = middleware.get_tools()
        save_memory = next(t for t in tools if t.name == "save_memory")

        result = save_memory._handler(
            filename="api.md",
            content="API notes",
            category="projects",
        )

        assert result["path"] == "/memories/projects/api.md"

    def test_recall_memory_tool(self, middleware, filesystem):
        """Test recall_memory tool."""
        filesystem.write_file("/memories/notes.txt", "Important notes here")

        tools = middleware.get_tools()
        recall_memory = next(t for t in tools if t.name == "recall_memory")

        result = recall_memory._handler(path="/memories/notes.txt")
        assert "Important notes here" in result["content"]

    def test_recall_memory_adds_prefix(self, middleware, filesystem):
        """Test recall_memory adds /memories/ prefix if missing."""
        filesystem.write_file("/memories/notes.txt", "Important notes here")

        tools = middleware.get_tools()
        recall_memory = next(t for t in tools if t.name == "recall_memory")

        result = recall_memory._handler(path="notes.txt")
        assert "Important notes here" in result["content"]

    def test_search_memories_tool(self, middleware, filesystem):
        """Test search_memories tool."""
        filesystem.write_file("/memories/file1.txt", "hello world")
        filesystem.write_file("/memories/file2.txt", "goodbye world")

        tools = middleware.get_tools()
        search_memories = next(t for t in tools if t.name == "search_memories")

        result = search_memories._handler(query="hello")
        assert len(result["matches"]) >= 1

    def test_update_agents_md_tool(self, middleware, filesystem):
        """Test update_agents_md tool."""
        tools = middleware.get_tools()
        update_agents_md = next(t for t in tools if t.name == "update_agents_md")

        result = update_agents_md._handler(
            content="# Updated Knowledge\n\nNew facts."
        )

        assert result["status"] == "updated"
        assert filesystem.exists("/memories/AGENTS.md")

        # Verify content
        read_result = filesystem.read_file("/memories/AGENTS.md")
        assert "Updated Knowledge" in read_result["content"]


class TestFactoryFunctions:
    """Test factory functions."""

    def test_create_memory_middleware_default(self):
        """Test creating memory middleware with defaults."""
        mw = create_memory_middleware()
        assert mw.memories_path == "/memories/"
        assert mw.agents_md_path == "/memories/AGENTS.md"

    def test_create_memory_middleware_custom(self):
        """Test creating memory middleware with custom paths."""
        mw = create_memory_middleware(
            memories_path="/custom/",
            agents_md_path="/custom/BRAIN.md",
        )
        assert mw.memories_path == "/custom/"
        assert mw.agents_md_path == "/custom/BRAIN.md"

    def test_create_composite_backend(self):
        """Test creating composite backend."""
        default = StateFilesystemBackend()
        composite = create_composite_backend(
            default_backend=default,
            memories_path="/tmp/test_memories",
            agent_id="test-agent",
        )

        assert isinstance(composite, CompositeBackend)
        assert "/memories/" in composite.routes


class TestCompositeBackendEdgeCases:
    """Test edge cases for CompositeBackend."""

    def test_multiple_routes(self):
        """Test multiple route prefixes."""
        default = StateFilesystemBackend()
        memories = StateFilesystemBackend()
        context = StateFilesystemBackend()

        composite = CompositeBackend(
            default=default,
            routes={
                "/memories/": memories,
                "/context/": context,
            },
        )

        composite.write_file("/memories/note.txt", "memory")
        composite.write_file("/context/data.txt", "context")
        composite.write_file("/workspace/file.txt", "default")

        assert memories.exists("/memories/note.txt")
        assert context.exists("/context/data.txt")
        assert default.exists("/workspace/file.txt")

    def test_longest_prefix_match(self):
        """Test that longest prefix wins."""
        default = StateFilesystemBackend()
        short = StateFilesystemBackend()
        long = StateFilesystemBackend()

        composite = CompositeBackend(
            default=default,
            routes={
                "/data/": short,
                "/data/special/": long,
            },
        )

        composite.write_file("/data/normal.txt", "short")
        composite.write_file("/data/special/file.txt", "long")

        assert short.exists("/data/normal.txt")
        assert long.exists("/data/special/file.txt")


class TestIntegrationMemoryAndContext:
    """Test memory and context integration."""

    @pytest.fixture
    def temp_dir(self):
        """Create temp directory."""
        path = tempfile.mkdtemp(prefix="vel_test_")
        yield path
        shutil.rmtree(path, ignore_errors=True)

    def test_memory_persists_across_backends(self, temp_dir):
        """Test that memories persist to disk."""
        # Create first composite backend
        default1 = StateFilesystemBackend()
        persistent = PersistentStoreBackend(base_path=temp_dir, agent_id="agent")
        composite1 = CompositeBackend(
            default=default1,
            routes={"/memories/": persistent},
        )

        # Write memory
        composite1.write_file("/memories/knowledge.txt", "Important fact")

        # Create new in-memory default (simulating session restart)
        default2 = StateFilesystemBackend()
        composite2 = CompositeBackend(
            default=default2,
            routes={"/memories/": persistent},  # Same persistent backend
        )

        # Memory should still be accessible
        assert composite2.exists("/memories/knowledge.txt")
        result = composite2.read_file("/memories/knowledge.txt")
        assert "Important fact" in result["content"]

        # But ephemeral files are gone
        composite1.write_file("/workspace/temp.txt", "Temporary")
        assert not composite2.exists("/workspace/temp.txt")
