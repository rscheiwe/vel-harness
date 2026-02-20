#!/usr/bin/env python3
import subprocess
import sys

# Execute the test runner script
result = subprocess.run(
    [sys.executable, '/Users/richard.s/vel-harness/run_parity_tests.py'],
    capture_output=True,
    text=True
)

# Print stdout
if result.stdout:
    print(result.stdout)

# Print stderr if any
if result.stderr:
    print("STDERR:", file=sys.stderr)
    print(result.stderr, file=sys.stderr)

# Exit with the same code
sys.exit(result.returncode)
