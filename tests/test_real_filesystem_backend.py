"""
Tests for RealFilesystemBackend path confinement.
"""

from pathlib import Path

from vel_harness.backends.real import RealFilesystemBackend


def test_base_path_confines_absolute_paths(tmp_path: Path) -> None:
    backend = RealFilesystemBackend(base_path=str(tmp_path))
    result = backend.write_file("/outside.txt", "x")
    # Absolute input is mapped under base path, not host root.
    assert result["status"] == "success"
    assert Path(result["path"]).name == "outside.txt"
    assert "error" not in backend.read_file("/outside.txt")


def test_escape_attempt_blocked(tmp_path: Path) -> None:
    backend = RealFilesystemBackend(base_path=str(tmp_path))
    result = backend.read_file("../escape.txt")
    assert "error" in result
    assert "escapes base_path" in result["error"]
