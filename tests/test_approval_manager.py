"""
Tests for parallel approval manager.
"""

import asyncio

import pytest

from vel_harness.approval import ApprovalManager


@pytest.mark.asyncio
async def test_respond_by_tool_args_resolves_exact_pending() -> None:
    mgr = ApprovalManager()
    seen = []

    async def request(tool: str, args: dict) -> bool:
        result = await mgr.request_approval(tool, args)
        seen.append((tool, args, result))
        return result

    task1 = asyncio.create_task(request("execute", {"command": "ls"}))
    task2 = asyncio.create_task(request("execute", {"command": "pwd"}))
    await asyncio.sleep(0)

    assert mgr.respond_by_tool_args("execute", {"command": "pwd"}, True)
    assert mgr.respond_by_tool_args("execute", {"command": "ls"}, False)

    r1 = await task1
    r2 = await task2
    assert sorted([r1, r2]) == [False, True]


@pytest.mark.asyncio
async def test_respond_by_tool_name_ambiguous_returns_false() -> None:
    mgr = ApprovalManager()
    t1 = asyncio.create_task(mgr.request_approval("execute", {"command": "ls"}))
    t2 = asyncio.create_task(mgr.request_approval("execute", {"command": "pwd"}))
    await asyncio.sleep(0)
    assert mgr.respond_by_tool_name("execute", True) is False
    mgr.clear()
    await asyncio.gather(t1, t2)
