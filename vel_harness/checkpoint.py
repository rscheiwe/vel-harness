"""
Vel Harness File Checkpointing - Track filesystem changes and support rewind.

Tracks file modifications (write, edit, delete) made by agent tools and
supports reverting to previous checkpoints.

Usage:
    from vel_harness.checkpoint import FileCheckpointManager

    mgr = FileCheckpointManager()
    cp_id = mgr.create_checkpoint()

    # ... agent makes file changes (recorded via tool wrapping) ...
    mgr.record_change("/path/to/file.py", "write", previous_content="old content")

    # Revert all changes since checkpoint
    reverted = mgr.rewind_to(cp_id, filesystem_backend)
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Protocol, runtime_checkable


@runtime_checkable
class RewindableBackend(Protocol):
    """Minimal interface for a backend that supports rewind operations."""

    def read_file(self, path: str, offset: int = 0, limit: int = 100) -> Dict[str, Any]:
        ...

    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        ...


@dataclass
class FileChange:
    """A recorded filesystem change.

    Attributes:
        path: Absolute or relative file path
        action: Type of change (write, edit, delete)
        previous_content: File content before the change (None for new files)
        new_content: File content after the change (None for deletes)
        timestamp: Unix timestamp of the change
    """

    path: str
    action: Literal["write", "edit", "delete"]
    previous_content: Optional[str] = None
    new_content: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class Checkpoint:
    """A filesystem checkpoint.

    Attributes:
        id: Unique checkpoint identifier
        label: Optional human-readable label
        changes_since: Changes recorded after this checkpoint was created
        created_at: Unix timestamp of checkpoint creation
    """

    id: str
    label: Optional[str] = None
    changes_since: List[FileChange] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


class FileCheckpointManager:
    """Tracks filesystem changes and supports revert to checkpoints.

    The manager maintains a stack of checkpoints. Changes are recorded
    into the most recent checkpoint's changes_since list. Rewinding
    replays changes in reverse order to restore previous state.

    Integration:
        - Factory wraps write_file/edit_file tools to call record_change()
        - HarnessSession exposes rewind_files() for user-facing rewind
    """

    def __init__(self) -> None:
        self._checkpoints: List[Checkpoint] = []
        self._all_changes: List[FileChange] = []

    @property
    def checkpoints(self) -> List[Checkpoint]:
        """Get all checkpoints (oldest first)."""
        return list(self._checkpoints)

    @property
    def all_changes(self) -> List[FileChange]:
        """Get all recorded changes (oldest first)."""
        return list(self._all_changes)

    @property
    def change_count(self) -> int:
        """Get total number of recorded changes."""
        return len(self._all_changes)

    def create_checkpoint(self, label: Optional[str] = None) -> str:
        """Create a checkpoint at the current state.

        Args:
            label: Optional human-readable label for the checkpoint

        Returns:
            Checkpoint ID
        """
        checkpoint = Checkpoint(
            id=str(uuid.uuid4()),
            label=label,
        )
        self._checkpoints.append(checkpoint)
        return checkpoint.id

    def get_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Get a checkpoint by ID.

        Args:
            checkpoint_id: The checkpoint ID to look up

        Returns:
            The Checkpoint, or None if not found
        """
        for cp in self._checkpoints:
            if cp.id == checkpoint_id:
                return cp
        return None

    def record_change(
        self,
        path: str,
        action: Literal["write", "edit", "delete"],
        previous_content: Optional[str] = None,
        new_content: Optional[str] = None,
    ) -> FileChange:
        """Record a filesystem change.

        Called by tool wrappers when write_file/edit_file/delete_file executes.

        Args:
            path: File path that was modified
            action: Type of change
            previous_content: Content before the change (None for new files)
            new_content: Content after the change (None for deletes)

        Returns:
            The recorded FileChange
        """
        change = FileChange(
            path=path,
            action=action,
            previous_content=previous_content,
            new_content=new_content,
        )
        self._all_changes.append(change)

        # Add to the most recent checkpoint's changes_since list
        if self._checkpoints:
            self._checkpoints[-1].changes_since.append(change)

        return change

    def rewind_to(
        self,
        checkpoint_id: str,
        backend: RewindableBackend,
    ) -> List[str]:
        """Revert all changes since the given checkpoint.

        Replays changes in reverse order:
        - write (new file): delete the file by writing empty content
        - write (overwrite): restore previous_content
        - edit: restore previous_content
        - delete: restore previous_content

        Args:
            checkpoint_id: The checkpoint to rewind to
            backend: Filesystem backend for writing restored content

        Returns:
            List of reverted file paths

        Raises:
            ValueError: If checkpoint_id is not found
        """
        # Find the checkpoint
        cp_index = None
        for i, cp in enumerate(self._checkpoints):
            if cp.id == checkpoint_id:
                cp_index = i
                break

        if cp_index is None:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")

        # Collect all changes from this checkpoint onwards
        changes_to_revert: List[FileChange] = []
        for cp in self._checkpoints[cp_index:]:
            changes_to_revert.extend(cp.changes_since)

        # Restore each changed file to its baseline at checkpoint creation.
        # For a given path, the first change after checkpoint contains the
        # baseline in previous_content.
        baseline_by_path: Dict[str, Optional[str]] = {}
        for change in changes_to_revert:
            if change.path not in baseline_by_path:
                baseline_by_path[change.path] = change.previous_content

        reverted_paths: List[str] = []
        for path, baseline_content in baseline_by_path.items():
            if baseline_content is not None:
                backend.write_file(path, baseline_content)
            else:
                # File did not exist at checkpoint.
                if hasattr(backend, "delete_file"):
                    try:
                        backend.delete_file(path)  # type: ignore[attr-defined]
                    except Exception:
                        backend.write_file(path, "")
                else:
                    backend.write_file(path, "")
            reverted_paths.append(path)

        # Remove checkpoints from the rewind point onwards
        self._checkpoints = self._checkpoints[:cp_index]

        # Remove reverted changes from _all_changes.
        reverted_ids = {id(c) for c in changes_to_revert}
        self._all_changes = [c for c in self._all_changes if id(c) not in reverted_ids]

        return reverted_paths

    def get_changes_since(self, checkpoint_id: str) -> List[FileChange]:
        """Get all changes since a given checkpoint.

        Args:
            checkpoint_id: The checkpoint ID

        Returns:
            List of FileChange objects since the checkpoint

        Raises:
            ValueError: If checkpoint_id is not found
        """
        cp_index = None
        for i, cp in enumerate(self._checkpoints):
            if cp.id == checkpoint_id:
                cp_index = i
                break

        if cp_index is None:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")

        changes: List[FileChange] = []
        for cp in self._checkpoints[cp_index:]:
            changes.extend(cp.changes_since)
        return changes

    def get_changed_files(self) -> List[str]:
        """Get list of all files that have been changed.

        Returns:
            Deduplicated list of file paths
        """
        seen: set = set()
        paths: List[str] = []
        for change in self._all_changes:
            if change.path not in seen:
                seen.add(change.path)
                paths.append(change.path)
        return paths

    def clear(self) -> None:
        """Clear all checkpoints and changes."""
        self._checkpoints.clear()
        self._all_changes.clear()
