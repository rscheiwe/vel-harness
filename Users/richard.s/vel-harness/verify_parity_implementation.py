#!/usr/bin/env python3
"""
Verification script that directly executes and tests the parity_math module
"""
import sys
import os
import subprocess

print("=" * 70)
print("VERIFICATION: Running parity_math tests")
print("=" * 70)

# First, let's try running pytest directly
test_dir = '/Users/richard.s/vel-harness/tmp/deepagents_parity'
test_file = 'test_parity_math.py'

print(f"\nAttempting to run pytest on {test_file}...")
print("-" * 70)

try:
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', test_file, '-v', '--tb=short'],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=30
    )
    
    print("STDOUT:")
    print(result.stdout)
    
    if result.stderr:
        print("\nSTDERR:")
        print(result.stderr)
    
    print("-" * 70)
    print(f"Exit code: {result.returncode}")
    
    if result.returncode == 0:
        print("✓ Pytest execution successful - all tests passed!")
    else:
        print("✗ Pytest execution failed or tests did not pass")
        
except subprocess.TimeoutExpired:
    print("✗ Test execution timed out")
    sys.exit(1)
except Exception as e:
    print(f"✗ Error running pytest: {e}")
    print("\nFalling back to direct test execution...")
    
    # Fallback: Direct execution
    sys.path.insert(0, test_dir)
    try:
        from parity_math import is_even
        
        print("\n" + "=" * 70)
        print("FALLBACK: Direct function testing")
        print("=" * 70)
        
        tests = [
            (2, True, "positive even"),
            (1, False, "positive odd"),
            (-2, True, "negative even"),
            (-1, False, "negative odd"),
            (0, True, "zero"),
            (1000000, True, "large even"),
            (1000001, False, "large odd"),
        ]
        
        passed = 0
        failed = 0
        
        for value, expected, desc in tests:
            result = is_even(value)
            if result == expected:
                print(f"✓ is_even({value}) = {result} ({desc})")
                passed += 1
            else:
                print(f"✗ is_even({value}) = {result}, expected {expected} ({desc})")
                failed += 1
        
        print("-" * 70)
        print(f"Results: {passed} passed, {failed} failed")
        
        if failed == 0:
            print("✓ All direct tests passed!")
            sys.exit(0)
        else:
            print("✗ Some tests failed")
            sys.exit(1)
            
    except Exception as e2:
        print(f"✗ Fallback also failed: {e2}")
        sys.exit(1)

print("=" * 70)
