"""
Tests for RealFilesystemBackend path confinement.
"""

from pathlib import Path

from vel_harness.backends.real import RealFilesystemBackend


def test_base_path_confines_absolute_paths(tmp_path: Path) -> None:
    backend = RealFilesystemBackend(base_path=str(tmp_path))
    inside = tmp_path / "inside.txt"
    result = backend.write_file(str(inside), "x")
    # Absolute path inside base path should be accepted as-is.
    assert result["status"] == "success"
    assert Path(result["path"]) == inside
    assert "error" not in backend.read_file(str(inside))


def test_absolute_outside_base_path_blocked(tmp_path: Path) -> None:
    backend = RealFilesystemBackend(base_path=str(tmp_path))
    result = backend.read_file("/tmp/outside.txt")
    assert "error" in result
    assert "escapes base_path" in result["error"]


def test_escape_attempt_blocked(tmp_path: Path) -> None:
    backend = RealFilesystemBackend(base_path=str(tmp_path))
    result = backend.read_file("../escape.txt")
    assert "error" in result
    assert "escapes base_path" in result["error"]
