#!/usr/bin/env python
"""Run pytest on test_strengthening_runtime.py"""
import subprocess
import sys

result = subprocess.run(
    ["pytest", "-q", "tests/test_strengthening_runtime.py"],
    capture_output=True,
    text=True,
    cwd="/Users/richard.s/vel-harness"
)

print(result.stdout)
print(result.stderr, file=sys.stderr)
sys.exit(result.returncode)
