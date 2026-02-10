#!/usr/bin/env python3
"""
VelHarness Feature Test Suite

Comprehensive tests for all harness capabilities.
Runs directly without an API server.

Usage:
    python examples/test_all_features.py

    # Run specific test
    python examples/test_all_features.py --test skill_loading

    # Run with streaming output
    python examples/test_all_features.py --stream

Requirements:
    - .env file with ANTHROPIC_API_KEY or environment variable
"""

import argparse
import asyncio
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Add parent to path for development
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env file
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from vel_harness import VelHarness, AgentConfig


@dataclass
class TestResult:
    """Result of a test case."""
    name: str
    passed: bool
    message: str
    response: str = ""


class HarnessTestSuite:
    """Test suite for VelHarness features."""

    def __init__(self, stream: bool = False):
        self.stream = stream
        self.skills_dir = Path(__file__).parent / "skills"
        self.work_dir = tempfile.mkdtemp(prefix="vel_test_")
        self.results: list[TestResult] = []

        # Create harness
        self.harness = VelHarness(
            model={
                "provider": "anthropic",
                "model": "claude-sonnet-4-5-20250929",
            },
            skill_dirs=[str(self.skills_dir)],
            working_directory=self.work_dir,
            sandbox=True,
            planning=True,
        )

    async def run_prompt(self, prompt: str, session_id: str = "test") -> str:
        """Run a prompt through the harness."""
        if self.stream:
            chunks = []
            async for event in self.harness.run_stream(prompt, session_id=session_id):
                if event.get("type") == "text-delta":
                    chunk = event.get("delta", "")
                    print(chunk, end="", flush=True)
                    chunks.append(chunk)
                elif event.get("type") == "tool-output-available":
                    print(f"\n  [Tool: {event.get('toolName', 'unknown')}]")
            print()  # Newline after streaming
            return "".join(chunks)
        else:
            return await self.harness.run(prompt, session_id=session_id)

    async def test_simple_response(self) -> TestResult:
        """Test basic question answering."""
        print("\n[Test] Simple Response")
        try:
            response = await self.run_prompt(
                "What is the capital of France? Reply with just the city name.",
                session_id="test-simple"
            )
            passed = "paris" in response.lower()
            return TestResult(
                name="Simple Response",
                passed=passed,
                message="Got expected response" if passed else "Unexpected response",
                response=response
            )
        except Exception as e:
            return TestResult(
                name="Simple Response",
                passed=False,
                message=f"Error: {e}"
            )

    async def test_bash_tool(self) -> TestResult:
        """Test bash command execution."""
        print("\n[Test] Bash Tool")
        try:
            response = await self.run_prompt(
                "Run the command 'echo BASH_TEST_OK' and tell me the output.",
                session_id="test-bash"
            )
            passed = "BASH_TEST_OK" in response
            return TestResult(
                name="Bash Tool",
                passed=passed,
                message="Bash executed successfully" if passed else "Output not found",
                response=response
            )
        except Exception as e:
            return TestResult(
                name="Bash Tool",
                passed=False,
                message=f"Error: {e}"
            )

    async def test_file_read(self) -> TestResult:
        """Test file reading."""
        print("\n[Test] File Read")
        try:
            # Create a test file
            test_file = Path(self.work_dir) / "test_read.txt"
            test_file.write_text("FILE_READ_CONTENT_OK")

            response = await self.run_prompt(
                f"Read the file at {test_file} and tell me its contents.",
                session_id="test-read"
            )
            passed = "FILE_READ_CONTENT_OK" in response
            return TestResult(
                name="File Read",
                passed=passed,
                message="File read successfully" if passed else "Content not found",
                response=response
            )
        except Exception as e:
            return TestResult(
                name="File Read",
                passed=False,
                message=f"Error: {e}"
            )

    async def test_file_write(self) -> TestResult:
        """Test file writing."""
        print("\n[Test] File Write")
        try:
            output_file = Path(self.work_dir) / "test_write.txt"

            response = await self.run_prompt(
                f"Write the text 'FILE_WRITE_OK' to {output_file}",
                session_id="test-write"
            )

            # Verify file was created
            passed = output_file.exists() and "FILE_WRITE_OK" in output_file.read_text()
            return TestResult(
                name="File Write",
                passed=passed,
                message="File written successfully" if passed else "File not found or wrong content",
                response=response
            )
        except Exception as e:
            return TestResult(
                name="File Write",
                passed=False,
                message=f"Error: {e}"
            )

    async def test_glob(self) -> TestResult:
        """Test glob file pattern matching."""
        print("\n[Test] Glob")
        try:
            response = await self.run_prompt(
                f"Find all .md files in {self.skills_dir} using glob",
                session_id="test-glob"
            )
            # Should find at least our test skills
            passed = ".md" in response.lower() or "skill" in response.lower()
            return TestResult(
                name="Glob",
                passed=passed,
                message="Glob found files" if passed else "No files found",
                response=response
            )
        except Exception as e:
            return TestResult(
                name="Glob",
                passed=False,
                message=f"Error: {e}"
            )

    async def test_grep(self) -> TestResult:
        """Test content search."""
        print("\n[Test] Grep")
        try:
            response = await self.run_prompt(
                f"Search for the word 'SKILL_TEST_PASS' in files under {self.skills_dir}",
                session_id="test-grep"
            )
            passed = "test_skill" in response.lower() or "found" in response.lower()
            return TestResult(
                name="Grep",
                passed=passed,
                message="Grep found content" if passed else "Content not found",
                response=response
            )
        except Exception as e:
            return TestResult(
                name="Grep",
                passed=False,
                message=f"Error: {e}"
            )

    async def test_skill_loading(self) -> TestResult:
        """Test skill loading (tool_result injection)."""
        print("\n[Test] Skill Loading")
        try:
            response = await self.run_prompt(
                "Load the 'Test Skill' and follow its verification instructions exactly.",
                session_id="test-skill"
            )
            # The skill instructs to say these phrases
            passed = "SKILL_LOADED_OK" in response or "SKILL_TEST_PASS" in response
            return TestResult(
                name="Skill Loading",
                passed=passed,
                message="Skill loaded and executed" if passed else "Skill instructions not followed",
                response=response
            )
        except Exception as e:
            return TestResult(
                name="Skill Loading",
                passed=False,
                message=f"Error: {e}"
            )

    async def test_todo_write(self) -> TestResult:
        """Test todo/planning tools."""
        print("\n[Test] Todo Write")
        try:
            response = await self.run_prompt(
                "Create a todo list with 3 items for 'learning Python': 1) Read basics, 2) Practice, 3) Build project",
                session_id="test-todo"
            )
            # Should mention todos or planning
            passed = "todo" in response.lower() or "1" in response
            return TestResult(
                name="Todo Write",
                passed=passed,
                message="Todos created" if passed else "Todo creation unclear",
                response=response
            )
        except Exception as e:
            return TestResult(
                name="Todo Write",
                passed=False,
                message=f"Error: {e}"
            )

    async def test_session_continuity(self) -> TestResult:
        """Test that session context is maintained."""
        print("\n[Test] Session Continuity")
        try:
            session_id = "test-continuity"

            # First message
            await self.run_prompt(
                "Remember the secret word: ELEPHANT",
                session_id=session_id
            )

            # Second message should remember
            response = await self.run_prompt(
                "What was the secret word I told you?",
                session_id=session_id
            )

            passed = "elephant" in response.lower()
            return TestResult(
                name="Session Continuity",
                passed=passed,
                message="Context maintained" if passed else "Context lost",
                response=response
            )
        except Exception as e:
            return TestResult(
                name="Session Continuity",
                passed=False,
                message=f"Error: {e}"
            )

    async def test_subagent_explore(self) -> TestResult:
        """Test explore subagent."""
        print("\n[Test] Subagent (Explore)")
        try:
            response = await self.run_prompt(
                f"Use an explore agent to investigate the structure of {self.skills_dir} and summarize what you find.",
                session_id="test-explore"
            )
            # Should mention files or structure
            passed = "skill" in response.lower() or "file" in response.lower()
            return TestResult(
                name="Subagent (Explore)",
                passed=passed,
                message="Explore agent worked" if passed else "No exploration results",
                response=response
            )
        except Exception as e:
            return TestResult(
                name="Subagent (Explore)",
                passed=False,
                message=f"Error: {e}"
            )

    async def test_subagent_plan(self) -> TestResult:
        """Test plan subagent."""
        print("\n[Test] Subagent (Plan)")
        try:
            response = await self.run_prompt(
                "Use a plan agent to create a structured plan for 'building a REST API'",
                session_id="test-plan"
            )
            # Should have structured output
            passed = any(word in response.lower() for word in ["step", "plan", "1.", "first"])
            return TestResult(
                name="Subagent (Plan)",
                passed=passed,
                message="Plan agent worked" if passed else "No plan generated",
                response=response
            )
        except Exception as e:
            return TestResult(
                name="Subagent (Plan)",
                passed=False,
                message=f"Error: {e}"
            )

    async def test_agent_registry(self) -> TestResult:
        """Test custom agent registration."""
        print("\n[Test] Agent Registry")
        try:
            # Register a custom agent
            self.harness.register_agent(
                "custom-test",
                AgentConfig(
                    name="custom-test",
                    system_prompt="You are a test agent. Always say CUSTOM_AGENT_OK.",
                    tools=["read_file"],
                    max_turns=5,
                )
            )

            agents = self.harness.list_agent_types()
            passed = "custom-test" in agents and "default" in agents and "explore" in agents

            return TestResult(
                name="Agent Registry",
                passed=passed,
                message=f"Agents: {agents}" if passed else "Agent not registered",
                response=str(agents)
            )
        except Exception as e:
            return TestResult(
                name="Agent Registry",
                passed=False,
                message=f"Error: {e}"
            )

    async def run_all(self) -> list[TestResult]:
        """Run all tests."""
        tests = [
            self.test_simple_response,
            self.test_bash_tool,
            self.test_file_read,
            self.test_file_write,
            self.test_glob,
            self.test_grep,
            self.test_skill_loading,
            self.test_todo_write,
            self.test_session_continuity,
            self.test_agent_registry,
            # Subagent tests are slower, run last
            self.test_subagent_explore,
            self.test_subagent_plan,
        ]

        for test_fn in tests:
            result = await test_fn()
            self.results.append(result)
            status = "✓" if result.passed else "✗"
            print(f"  {status} {result.name}: {result.message}")

        return self.results

    async def run_single(self, test_name: str) -> Optional[TestResult]:
        """Run a single test by name."""
        test_map = {
            "simple": self.test_simple_response,
            "bash": self.test_bash_tool,
            "read": self.test_file_read,
            "write": self.test_file_write,
            "glob": self.test_glob,
            "grep": self.test_grep,
            "skill": self.test_skill_loading,
            "todo": self.test_todo_write,
            "session": self.test_session_continuity,
            "explore": self.test_subagent_explore,
            "plan": self.test_subagent_plan,
            "registry": self.test_agent_registry,
        }

        test_fn = test_map.get(test_name.lower())
        if not test_fn:
            print(f"Unknown test: {test_name}")
            print(f"Available: {', '.join(test_map.keys())}")
            return None

        result = await test_fn()
        self.results.append(result)
        return result

    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)

        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)

        for result in self.results:
            status = "PASS" if result.passed else "FAIL"
            print(f"  [{status}] {result.name}: {result.message}")

        print("-" * 60)
        print(f"Results: {passed}/{total} passed")

        if passed == total:
            print("All tests passed! ✓")
        else:
            print(f"Failed: {total - passed} tests")


async def main():
    parser = argparse.ArgumentParser(description="VelHarness Feature Tests")
    parser.add_argument("--test", "-t", help="Run specific test (e.g., skill, bash, read)")
    parser.add_argument("--stream", "-s", action="store_true", help="Show streaming output")
    args = parser.parse_args()

    # Check API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    print("=" * 60)
    print("VelHarness Feature Test Suite")
    print("=" * 60)

    suite = HarnessTestSuite(stream=args.stream)

    if args.test:
        result = await suite.run_single(args.test)
        if result:
            status = "PASS" if result.passed else "FAIL"
            print(f"\n[{status}] {result.name}: {result.message}")
            if not result.passed:
                print(f"Response: {result.response[:500]}...")
    else:
        await suite.run_all()
        suite.print_summary()


if __name__ == "__main__":
    asyncio.run(main())
