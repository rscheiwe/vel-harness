#!/usr/bin/env python3
import subprocess
import sys

# Execute the run_parity_tests.py script
result = subprocess.run(
    [sys.executable, '/Users/richard.s/vel-harness/run_parity_tests.py'],
    capture_output=True,
    text=True
)

# Print stdout
print(result.stdout, end='')

# Print stderr if any
if result.stderr:
    print(result.stderr, end='', file=sys.stderr)

# Exit with the same code as the subprocess
sys.exit(result.returncode)
