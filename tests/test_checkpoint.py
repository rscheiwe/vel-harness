"""
Tests for File Checkpointing / Rewind (WS8)

Tests the FileCheckpointManager including:
- FileChange and Checkpoint creation
- create_checkpoint() returns unique IDs
- record_change() tracks write/edit/delete with previous content
- rewind_to() restores previous content
- rewind_to() clears newly created files
- Multiple checkpoints with selective rewind
- LIFO revert ordering (most recent change first)
- get_changes_since() and get_changed_files()
- HarnessSession.create_checkpoint() and rewind_files()
- VelHarness integration (checkpoint_manager property)
"""

import time
import pytest
from unittest.mock import MagicMock, patch

from vel_harness.checkpoint import (
    FileChange,
    FileCheckpointManager,
    Checkpoint,
)
from vel_harness.session import HarnessSession
from vel_harness import VelHarness


# --- Helpers ---


class MockBackend:
    """Mock filesystem backend for testing rewind."""

    def __init__(self, files=None):
        self.files = dict(files) if files else {}
        self.write_calls = []

    def read_file(self, path, offset=0, limit=100):
        if path in self.files:
            return {"content": self.files[path], "path": path}
        return {"error": "File not found", "path": path}

    def write_file(self, path, content):
        self.write_calls.append({"path": path, "content": content})
        self.files[path] = content
        return {"status": "ok", "path": path}


# --- FileChange Tests ---


class TestFileChange:
    """Tests for FileChange dataclass."""

    def test_write_change(self):
        change = FileChange(path="/test.py", action="write", new_content="hello")
        assert change.path == "/test.py"
        assert change.action == "write"
        assert change.previous_content is None
        assert change.new_content == "hello"
        assert change.timestamp > 0

    def test_edit_change(self):
        change = FileChange(
            path="/test.py",
            action="edit",
            previous_content="old",
            new_content="new",
        )
        assert change.action == "edit"
        assert change.previous_content == "old"
        assert change.new_content == "new"

    def test_delete_change(self):
        change = FileChange(
            path="/test.py",
            action="delete",
            previous_content="content before delete",
        )
        assert change.action == "delete"
        assert change.previous_content == "content before delete"
        assert change.new_content is None

    def test_timestamp_auto_generated(self):
        before = time.time()
        change = FileChange(path="/test.py", action="write")
        after = time.time()
        assert before <= change.timestamp <= after


# --- Checkpoint Tests ---


class TestCheckpoint:
    """Tests for Checkpoint dataclass."""

    def test_checkpoint_defaults(self):
        cp = Checkpoint(id="test-id")
        assert cp.id == "test-id"
        assert cp.label is None
        assert cp.changes_since == []
        assert cp.created_at > 0

    def test_checkpoint_with_label(self):
        cp = Checkpoint(id="test-id", label="before refactor")
        assert cp.label == "before refactor"


# --- FileCheckpointManager Core Tests ---


class TestCheckpointManager:
    """Tests for FileCheckpointManager core operations."""

    def test_initial_state(self):
        mgr = FileCheckpointManager()
        assert mgr.checkpoints == []
        assert mgr.all_changes == []
        assert mgr.change_count == 0

    def test_create_checkpoint(self):
        mgr = FileCheckpointManager()
        cp_id = mgr.create_checkpoint()
        assert cp_id is not None
        assert len(mgr.checkpoints) == 1
        assert mgr.checkpoints[0].id == cp_id

    def test_create_checkpoint_with_label(self):
        mgr = FileCheckpointManager()
        cp_id = mgr.create_checkpoint(label="initial")
        cp = mgr.get_checkpoint(cp_id)
        assert cp is not None
        assert cp.label == "initial"

    def test_multiple_checkpoints_unique_ids(self):
        mgr = FileCheckpointManager()
        id1 = mgr.create_checkpoint()
        id2 = mgr.create_checkpoint()
        id3 = mgr.create_checkpoint()
        assert id1 != id2 != id3
        assert len(mgr.checkpoints) == 3

    def test_get_checkpoint_not_found(self):
        mgr = FileCheckpointManager()
        assert mgr.get_checkpoint("nonexistent") is None

    def test_record_change(self):
        mgr = FileCheckpointManager()
        change = mgr.record_change("/test.py", "write", new_content="hello")
        assert isinstance(change, FileChange)
        assert change.path == "/test.py"
        assert mgr.change_count == 1

    def test_record_change_without_checkpoint(self):
        """Changes recorded without a checkpoint are tracked globally."""
        mgr = FileCheckpointManager()
        mgr.record_change("/a.py", "write", new_content="a")
        mgr.record_change("/b.py", "write", new_content="b")
        assert mgr.change_count == 2
        assert len(mgr.all_changes) == 2

    def test_record_change_added_to_latest_checkpoint(self):
        """Changes after checkpoint are added to that checkpoint's list."""
        mgr = FileCheckpointManager()
        cp_id = mgr.create_checkpoint()
        mgr.record_change("/test.py", "write", new_content="hello")

        cp = mgr.get_checkpoint(cp_id)
        assert len(cp.changes_since) == 1
        assert cp.changes_since[0].path == "/test.py"

    def test_changes_go_to_most_recent_checkpoint(self):
        """Changes go to the most recently created checkpoint."""
        mgr = FileCheckpointManager()
        cp1_id = mgr.create_checkpoint()
        mgr.record_change("/a.py", "write")
        cp2_id = mgr.create_checkpoint()
        mgr.record_change("/b.py", "write")

        cp1 = mgr.get_checkpoint(cp1_id)
        cp2 = mgr.get_checkpoint(cp2_id)
        assert len(cp1.changes_since) == 1
        assert cp1.changes_since[0].path == "/a.py"
        assert len(cp2.changes_since) == 1
        assert cp2.changes_since[0].path == "/b.py"

    def test_get_changed_files(self):
        mgr = FileCheckpointManager()
        mgr.record_change("/a.py", "write")
        mgr.record_change("/b.py", "edit")
        mgr.record_change("/a.py", "edit")  # Duplicate path
        assert mgr.get_changed_files() == ["/a.py", "/b.py"]

    def test_clear(self):
        mgr = FileCheckpointManager()
        mgr.create_checkpoint()
        mgr.record_change("/test.py", "write")
        mgr.clear()
        assert mgr.checkpoints == []
        assert mgr.all_changes == []
        assert mgr.change_count == 0


# --- Rewind Tests ---


class TestRewind:
    """Tests for FileCheckpointManager.rewind_to()."""

    def test_rewind_restores_overwritten_file(self):
        """Rewind restores file content that was overwritten."""
        mgr = FileCheckpointManager()
        backend = MockBackend(files={"/test.py": "restored content"})

        cp_id = mgr.create_checkpoint()
        mgr.record_change("/test.py", "write", previous_content="original", new_content="new")

        reverted = mgr.rewind_to(cp_id, backend)
        assert "/test.py" in reverted
        assert backend.files["/test.py"] == "original"

    def test_rewind_clears_new_file(self):
        """Rewind writes empty content for files that didn't exist before."""
        mgr = FileCheckpointManager()
        backend = MockBackend(files={"/new.py": "content"})

        cp_id = mgr.create_checkpoint()
        mgr.record_change("/new.py", "write", previous_content=None, new_content="content")

        reverted = mgr.rewind_to(cp_id, backend)
        assert "/new.py" in reverted
        assert backend.files["/new.py"] == ""  # Cleared

    def test_rewind_restores_edited_file(self):
        """Rewind restores file content after edit."""
        mgr = FileCheckpointManager()
        backend = MockBackend()

        cp_id = mgr.create_checkpoint()
        mgr.record_change(
            "/test.py", "edit",
            previous_content="def foo():\n    pass",
            new_content="def foo():\n    return 42",
        )

        reverted = mgr.rewind_to(cp_id, backend)
        assert backend.files["/test.py"] == "def foo():\n    pass"

    def test_rewind_restores_deleted_file(self):
        """Rewind restores deleted file."""
        mgr = FileCheckpointManager()
        backend = MockBackend()

        cp_id = mgr.create_checkpoint()
        mgr.record_change(
            "/deleted.py", "delete",
            previous_content="important content",
        )

        reverted = mgr.rewind_to(cp_id, backend)
        assert backend.files["/deleted.py"] == "important content"

    def test_rewind_multiple_files(self):
        """Rewind restores multiple files."""
        mgr = FileCheckpointManager()
        backend = MockBackend()

        cp_id = mgr.create_checkpoint()
        mgr.record_change("/a.py", "write", previous_content="a_orig", new_content="a_new")
        mgr.record_change("/b.py", "write", previous_content="b_orig", new_content="b_new")
        mgr.record_change("/c.py", "edit", previous_content="c_orig", new_content="c_new")

        reverted = mgr.rewind_to(cp_id, backend)
        assert len(reverted) == 3
        assert backend.files["/a.py"] == "a_orig"
        assert backend.files["/b.py"] == "b_orig"
        assert backend.files["/c.py"] == "c_orig"

    def test_rewind_lifo_order(self):
        """Rewind restores path to checkpoint baseline across multiple edits."""
        mgr = FileCheckpointManager()
        backend = MockBackend()

        cp_id = mgr.create_checkpoint()
        # Write then edit same file — rewind should restore to state before write
        mgr.record_change("/test.py", "write", previous_content="original", new_content="written")
        mgr.record_change("/test.py", "edit", previous_content="written", new_content="edited")

        reverted = mgr.rewind_to(cp_id, backend)
        # Only one restore per path, but content should be checkpoint baseline.
        assert len(reverted) == 1
        assert backend.files["/test.py"] == "original"

    def test_rewind_removes_checkpoints(self):
        """Rewind removes checkpoints from the rewind point onwards."""
        mgr = FileCheckpointManager()
        backend = MockBackend()

        cp1_id = mgr.create_checkpoint(label="first")
        mgr.record_change("/a.py", "write", previous_content="a", new_content="a2")
        cp2_id = mgr.create_checkpoint(label="second")
        mgr.record_change("/b.py", "write", previous_content="b", new_content="b2")

        mgr.rewind_to(cp1_id, backend)
        # Both checkpoints should be removed (cp1 and cp2)
        assert len(mgr.checkpoints) == 0

    def test_rewind_to_middle_checkpoint(self):
        """Rewind to a middle checkpoint preserves earlier checkpoints."""
        mgr = FileCheckpointManager()
        backend = MockBackend()

        cp1_id = mgr.create_checkpoint(label="first")
        mgr.record_change("/a.py", "write", previous_content="a1", new_content="a2")
        cp2_id = mgr.create_checkpoint(label="second")
        mgr.record_change("/b.py", "write", previous_content="b1", new_content="b2")
        cp3_id = mgr.create_checkpoint(label="third")
        mgr.record_change("/c.py", "write", previous_content="c1", new_content="c2")

        # Rewind to cp2 — should revert /b.py and /c.py changes
        mgr.rewind_to(cp2_id, backend)

        # cp1 preserved, cp2 and cp3 removed
        assert len(mgr.checkpoints) == 1
        assert mgr.checkpoints[0].id == cp1_id
        # /b.py and /c.py reverted
        assert backend.files["/b.py"] == "b1"
        assert backend.files["/c.py"] == "c1"

    def test_rewind_invalid_checkpoint_raises(self):
        """Rewind with invalid checkpoint ID raises ValueError."""
        mgr = FileCheckpointManager()
        backend = MockBackend()

        with pytest.raises(ValueError, match="Checkpoint not found"):
            mgr.rewind_to("nonexistent", backend)

    def test_get_changes_since(self):
        """get_changes_since returns changes from checkpoint onwards."""
        mgr = FileCheckpointManager()

        cp1_id = mgr.create_checkpoint()
        mgr.record_change("/a.py", "write")
        cp2_id = mgr.create_checkpoint()
        mgr.record_change("/b.py", "write")
        mgr.record_change("/c.py", "edit")

        changes_since_cp1 = mgr.get_changes_since(cp1_id)
        assert len(changes_since_cp1) == 3

        changes_since_cp2 = mgr.get_changes_since(cp2_id)
        assert len(changes_since_cp2) == 2

    def test_get_changes_since_invalid_raises(self):
        mgr = FileCheckpointManager()
        with pytest.raises(ValueError, match="Checkpoint not found"):
            mgr.get_changes_since("nonexistent")

    def test_rewind_with_no_changes(self):
        """Rewind with no changes since checkpoint is a no-op."""
        mgr = FileCheckpointManager()
        backend = MockBackend()

        cp_id = mgr.create_checkpoint()
        # No changes recorded
        reverted = mgr.rewind_to(cp_id, backend)
        assert reverted == []
        assert backend.write_calls == []


# --- HarnessSession Integration Tests ---


class TestSessionCheckpoint:
    """Tests for HarnessSession checkpoint/rewind methods."""

    def _make_mock_harness(self):
        """Create a mock harness with checkpoint manager and filesystem."""
        harness = MagicMock()
        harness.checkpoint_manager = FileCheckpointManager()
        harness.deep_agent = MagicMock()
        harness.deep_agent.agent = MagicMock()
        harness.deep_agent.agent.model_cfg = {"provider": "anthropic", "model": "test"}

        # Mock filesystem middleware with backend
        fs_middleware = MagicMock()
        fs_middleware._backend = MockBackend(files={
            "/existing.py": "original content",
        })
        harness.deep_agent.middlewares = {"filesystem": fs_middleware}
        harness._reasoning_config = None
        return harness

    def test_create_checkpoint(self):
        harness = self._make_mock_harness()
        session = HarnessSession(harness=harness)
        cp_id = session.create_checkpoint(label="test")
        assert cp_id is not None
        assert len(harness.checkpoint_manager.checkpoints) == 1

    def test_rewind_files(self):
        harness = self._make_mock_harness()
        session = HarnessSession(harness=harness)

        cp_id = session.create_checkpoint()
        harness.checkpoint_manager.record_change(
            "/existing.py", "write",
            previous_content="original content",
            new_content="modified",
        )

        reverted = session.rewind_files(cp_id)
        assert "/existing.py" in reverted

        backend = harness.deep_agent.middlewares["filesystem"]._backend
        assert backend.files["/existing.py"] == "original content"

    def test_get_changed_files(self):
        harness = self._make_mock_harness()
        session = HarnessSession(harness=harness)

        harness.checkpoint_manager.record_change("/a.py", "write")
        harness.checkpoint_manager.record_change("/b.py", "edit")

        assert session.get_changed_files() == ["/a.py", "/b.py"]

    def test_get_state_includes_checkpoint_info(self):
        harness = self._make_mock_harness()
        session = HarnessSession(harness=harness)

        session.create_checkpoint()
        harness.checkpoint_manager.record_change("/a.py", "write")

        state = session.get_state()
        assert state["checkpoints"] == 1
        assert state["changes"] == 1

    def test_rewind_no_filesystem_raises(self):
        """Rewind raises RuntimeError when no filesystem backend."""
        harness = MagicMock()
        harness.checkpoint_manager = FileCheckpointManager()
        harness.deep_agent = MagicMock()
        harness.deep_agent.agent = MagicMock()
        harness.deep_agent.agent.model_cfg = {"provider": "anthropic", "model": "test"}
        harness.deep_agent.middlewares = {}  # No filesystem
        harness._reasoning_config = None

        session = HarnessSession(harness=harness)
        cp_id = session.create_checkpoint()
        harness.checkpoint_manager.record_change("/test.py", "write", new_content="x")

        with pytest.raises(RuntimeError, match="No filesystem backend"):
            session.rewind_files(cp_id)


# --- VelHarness Integration Tests ---


class TestVelHarnessCheckpoint:
    """Tests for checkpoint through VelHarness."""

    @pytest.fixture
    def mock_agent(self):
        with patch("vel_harness.factory.Agent") as MockAgent:
            mock_instance = MagicMock()
            MockAgent.return_value = mock_instance
            yield MockAgent

    def test_checkpoint_manager_exists(self, mock_agent):
        """Test VelHarness always creates a checkpoint manager."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
        )
        assert harness.checkpoint_manager is not None
        assert isinstance(harness.checkpoint_manager, FileCheckpointManager)

    def test_checkpoint_manager_on_deep_agent(self, mock_agent):
        """Test checkpoint manager is attached to deep agent."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
        )
        assert harness.deep_agent.checkpoint_manager is not None

    def test_session_uses_harness_checkpoint(self, mock_agent):
        """Test session's checkpoint methods use the harness checkpoint manager."""
        harness = VelHarness(
            model={"provider": "anthropic", "model": "test"},
        )
        session = harness.create_session()
        cp_id = session.create_checkpoint()
        assert len(harness.checkpoint_manager.checkpoints) == 1
