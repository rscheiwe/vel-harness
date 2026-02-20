#!/usr/bin/env python3
"""
Lightweight smoke checks for vel_harness internals.

Runs without external API calls and without pytest. Useful when test runners
are unavailable in constrained environments.
"""

from __future__ import annotations

import asyncio
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

from vel import ToolSpec

from vel_harness import VelHarness
from vel_harness.approval import ApprovalManager
from vel_harness.backends.real import RealFilesystemBackend
from vel_harness.checkpoint import FileCheckpointManager
from vel_harness.middleware.caching import CacheConfig, ToolCachingMiddleware
from vel_harness.middleware.retry import RetryConfig, ToolRetryMiddleware
from vel_harness.subagents.spawner import SubagentConfig, SubagentSpawner, SubagentStatus


async def check_caching_wrapper() -> None:
    calls = 0

    async def handler() -> dict:
        nonlocal calls
        calls += 1
        return {"ok": True}

    mw = ToolCachingMiddleware(
        CacheConfig(tool_cache_enabled=True, cacheable_tools={"cache_test"})
    )
    wrapped = mw.wrap_tool(ToolSpec.from_function(handler, name="cache_test"))
    await wrapped._handler()
    await wrapped._handler()
    assert calls == 1


async def check_retry_wrapper() -> None:
    calls = 0

    async def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise RuntimeError("transient")
        return "ok"

    mw = ToolRetryMiddleware(RetryConfig(max_retries=2, backoff_base=0.001))
    wrapped = mw.wrap_tool(ToolSpec.from_function(flaky, name="retry_test"))
    assert await wrapped._handler() == "ok"
    assert calls == 2


async def check_approval_manager() -> None:
    mgr = ApprovalManager()
    t1 = asyncio.create_task(mgr.request_approval("execute", {"command": "ls"}))
    t2 = asyncio.create_task(mgr.request_approval("execute", {"command": "pwd"}))
    await asyncio.sleep(0)
    assert mgr.respond_by_tool_args("execute", {"command": "pwd"}, True)
    assert mgr.respond_by_tool_args("execute", {"command": "ls"}, False)
    assert sorted([await t1, await t2]) == [False, True]


def check_real_filesystem_scope() -> None:
    with tempfile.TemporaryDirectory() as td:
        fs = RealFilesystemBackend(base_path=td)
        result = fs.write_file("/scoped.txt", "x")
        assert result["status"] == "success"
        escaped = fs.read_file("../escape.txt")
        assert "error" in escaped and "escapes base_path" in escaped["error"]


def check_checkpoint_restore_baseline() -> None:
    mgr = FileCheckpointManager()

    class Backend:
        def __init__(self) -> None:
            self.files = {}

        def read_file(self, path: str, offset: int = 0, limit: int = 100):
            return {"content": self.files.get(path, "")}

        def write_file(self, path: str, content: str):
            self.files[path] = content
            return {"status": "ok"}

    backend = Backend()
    cp = mgr.create_checkpoint()
    mgr.record_change("/a.txt", "write", previous_content="v1", new_content="v2")
    mgr.record_change("/a.txt", "edit", previous_content="v2", new_content="v3")
    mgr.rewind_to(cp, backend)
    assert backend.files["/a.txt"] == "v1"


async def check_subagent_contract() -> None:
    spawner = SubagentSpawner()
    with patch("vel_harness.subagents.spawner.Agent") as MockAgent:
        agent_instance = MagicMock()
        agent_instance.run = AsyncMock(return_value=MagicMock(content="ok", messages=[]))
        MockAgent.return_value = agent_instance
        result = await spawner._run_subagent(
            "subagent_abc",
            "task",
            SubagentConfig(model={"provider": "anthropic", "model": "x"}, timeout=1.0),
        )
        assert result.status == SubagentStatus.COMPLETED
        args, kwargs = agent_instance.run.call_args
        assert args[0] == {"message": "task"}
        assert "max_turns" not in kwargs


def check_harness_init() -> None:
    harness = VelHarness(
        model={"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
        sandbox=False,
    )
    assert harness.config.sandbox.fallback_unsandboxed is True
    assert harness.deep_agent is not None


async def main() -> None:
    check_harness_init()
    check_real_filesystem_scope()
    check_checkpoint_restore_baseline()
    await check_caching_wrapper()
    await check_retry_wrapper()
    await check_approval_manager()
    await check_subagent_contract()
    print("smoke_harness: OK")


if __name__ == "__main__":
    asyncio.run(main())
