#!/usr/bin/env python3
import subprocess
import sys

try:
    result = subprocess.run(
        [sys.executable, '/Users/richard.s/vel-harness/run_parity_tests.py'],
        capture_output=True,
        text=True,
        timeout=30
    )
    
    print("=== STDOUT ===")
    print(result.stdout)
    
    if result.stderr:
        print("\n=== STDERR ===")
        print(result.stderr)
    
    print(f"\n=== EXIT CODE: {result.returncode} ===")
    
except subprocess.TimeoutExpired:
    print("ERROR: Test execution timed out after 30 seconds")
except Exception as e:
    print(f"ERROR: Failed to execute test: {e}")
