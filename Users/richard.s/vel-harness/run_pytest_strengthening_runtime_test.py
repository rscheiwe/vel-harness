#!/usr/bin/env python3
import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-m", "pytest", "-q", "tests/test_strengthening_runtime.py"],
    capture_output=True,
    text=True,
    cwd="/Users/richard.s/vel-harness"
)

print(result.stdout)
print(result.stderr)
sys.exit(result.returncode)
