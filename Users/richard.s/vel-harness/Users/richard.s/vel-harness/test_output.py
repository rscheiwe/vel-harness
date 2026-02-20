#!/usr/bin/env python3
import sys
import os

# Add the deepagents_parity directory to Python path
sys.path.insert(0, '/Users/richard.s/vel-harness/tmp/deepagents_parity')

try:
    from parity_math import is_even

    print("Testing parity_math.is_even function...")
    print("-" * 60)

    tests_passed = 0
    tests_failed = 0

    def run_test(description, value, expected):
        global tests_passed, tests_failed
        try:
            result = is_even(value)
            if result == expected:
                print(f"✓ {description}: is_even({value}) = {result}")
                tests_passed += 1
            else:
                print(f"✗ {description}: is_even({value}) = {result}, expected {expected}")
                tests_failed += 1
        except Exception as e:
            print(f"✗ {description} failed with exception: {e}")
            tests_failed += 1

    # Happy path: Positive even numbers
    run_test("Positive even (2)", 2, True)
    run_test("Positive even (4)", 4, True)
    run_test("Positive even (100)", 100, True)

    # Happy path: Positive odd numbers
    run_test("Positive odd (1)", 1, False)
    run_test("Positive odd (3)", 3, False)
    run_test("Positive odd (99)", 99, False)

    # Happy path: Negative even numbers
    run_test("Negative even (-2)", -2, True)
    run_test("Negative even (-4)", -4, True)
    run_test("Negative even (-100)", -100, True)

    # Happy path: Negative odd numbers
    run_test("Negative odd (-1)", -1, False)
    run_test("Negative odd (-3)", -3, False)
    run_test("Negative odd (-99)", -99, False)

    # Edge case: Zero
    run_test("Zero", 0, True)

    # Edge case: Large numbers
    run_test("Large even (1000000)", 1000000, True)
    run_test("Large odd (1000001)", 1000001, False)
    run_test("Large negative even (-1000000)", -1000000, True)
    run_test("Large negative odd (-1000001)", -1000001, False)

    print("-" * 60)
    print(f"\n{tests_passed} passed, {tests_failed} failed")

    if tests_failed == 0:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print(f"\n✗ {tests_failed} test(s) failed")
        sys.exit(1)

except ImportError as e:
    print(f"ERROR: Could not import parity_math: {e}")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: Unexpected error: {e}")
    sys.exit(1)
