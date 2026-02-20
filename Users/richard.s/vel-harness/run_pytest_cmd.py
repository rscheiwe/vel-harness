#!/usr/bin/env python3
import subprocess
import sys

result = subprocess.run(
    ["pytest", "-q", "tests/test_strengthening_runtime.py"],
    cwd="/Users/richard.s/vel-harness",
    capture_output=True,
    text=True
)

print(result.stdout)
print(result.stderr)
sys.exit(result.returncode)
