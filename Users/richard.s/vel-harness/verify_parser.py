#!/usr/bin/env python3
"""Verification script for behavior_parser.parse_pair function"""
import sys
import os

# Try both possible paths
paths = [
    '/Users/richard.s/vel-harness/tmp',
    '/Users/richard.s/vel-harness/Users/richard.s/vel-harness/tmp'
]

behavior_parser = None
for path in paths:
    if os.path.exists(os.path.join(path, 'behavior_parser.py')):
        sys.path.insert(0, path)
        try:
            import behavior_parser
            print(f"✓ Successfully imported from: {path}")
            break
        except ImportError:
            continue

if behavior_parser is None:
    print("✗ ERROR: Could not import behavior_parser module")
    sys.exit(1)

from behavior_parser import parse_pair

print("\n" + "="*60)
print("Testing behavior_parser.parse_pair()")
print("="*60)

passed = 0
failed = 0

# Test 1: Simple k=v
print("\nTest 1: parse_pair('k=v')")
try:
    result = parse_pair('k=v')
    expected = ('k', 'v')
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"  ✓ PASS: {result}")
    passed += 1
except Exception as e:
    print(f"  ✗ FAIL: {e}")
    failed += 1

# Test 2: Empty value
print("\nTest 2: parse_pair('key=')")
try:
    result = parse_pair('key=')
    expected = ('key', '')
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"  ✓ PASS: {result}")
    passed += 1
except Exception as e:
    print(f"  ✗ FAIL: {e}")
    failed += 1

# Test 3: Empty key
print("\nTest 3: parse_pair('=value')")
try:
    result = parse_pair('=value')
    expected = ('', 'value')
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"  ✓ PASS: {result}")
    passed += 1
except Exception as e:
    print(f"  ✗ FAIL: {e}")
    failed += 1

# Test 4: Multiple equals in value
print("\nTest 4: parse_pair('key=value=with=equals')")
try:
    result = parse_pair('key=value=with=equals')
    expected = ('key', 'value=with=equals')
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"  ✓ PASS: {result}")
    passed += 1
except Exception as e:
    print(f"  ✗ FAIL: {e}")
    failed += 1

# Test 5: Missing equals (should raise ValueError)
print("\nTest 5: parse_pair('invalid') - should raise ValueError")
try:
    result = parse_pair('invalid')
    print(f"  ✗ FAIL: Should have raised ValueError, got {result}")
    failed += 1
except ValueError as e:
    if "missing '='" in str(e):
        print(f"  ✓ PASS: Correctly raised ValueError: {e}")
        passed += 1
    else:
        print(f"  ✗ FAIL: Wrong error message: {e}")
        failed += 1
except Exception as e:
    print(f"  ✗ FAIL: Wrong exception type: {e}")
    failed += 1

# Test 6: Complex values
print("\nTest 6: parse_pair('username=john.doe@example.com')")
try:
    result = parse_pair('username=john.doe@example.com')
    expected = ('username', 'john.doe@example.com')
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"  ✓ PASS: {result}")
    passed += 1
except Exception as e:
    print(f"  ✗ FAIL: {e}")
    failed += 1

print("\n" + "="*60)
print(f"RESULTS: {passed} passed, {failed} failed")
print("="*60)

if failed == 0:
    print("\n✓ All tests passed!")
    sys.exit(0)
else:
    print(f"\n✗ {failed} test(s) failed")
    sys.exit(1)
