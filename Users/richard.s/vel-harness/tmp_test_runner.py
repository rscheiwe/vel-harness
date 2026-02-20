#!/usr/bin/env python3
import sys
import os

# Add the tmp directory to Python path
sys.path.insert(0, '/Users/richard.s/vel-harness/tmp')

try:
    from behavior_parser import parse_pair
    
    print("Testing behavior_parser.parse_pair function...")
    print("-" * 50)
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: Simple k=v pair
    try:
        result = parse_pair('k=v')
        assert result == ('k', 'v'), f"Expected ('k', 'v'), got {result}"
        print("✓ test_parse_simple_pair('k=v') passed")
        tests_passed += 1
    except Exception as e:
        print(f"✗ test_parse_simple_pair failed: {e}")
        tests_failed += 1
    
    # Test 2: Empty value
    try:
        result = parse_pair('key=')
        assert result == ('key', ''), f"Expected ('key', ''), got {result}"
        print("✓ test_parse_pair_with_empty_value passed")
        tests_passed += 1
    except Exception as e:
        print(f"✗ test_parse_pair_with_empty_value failed: {e}")
        tests_failed += 1
    
    # Test 3: Empty key
    try:
        result = parse_pair('=value')
        assert result == ('', 'value'), f"Expected ('', 'value'), got {result}"
        print("✓ test_parse_pair_with_empty_key passed")
        tests_passed += 1
    except Exception as e:
        print(f"✗ test_parse_pair_with_empty_key failed: {e}")
        tests_failed += 1
    
    # Test 4: Value with equals signs
    try:
        result = parse_pair('key=value=with=equals')
        assert result == ('key', 'value=with=equals'), f"Expected ('key', 'value=with=equals'), got {result}"
        print("✓ test_parse_pair_with_equals_in_value passed")
        tests_passed += 1
    except Exception as e:
        print(f"✗ test_parse_pair_with_equals_in_value failed: {e}")
        tests_failed += 1
    
    # Test 5: Missing equals (should raise ValueError)
    try:
        parse_pair('invalid')
        print("✗ test_parse_pair_no_equals failed: Should have raised ValueError")
        tests_failed += 1
    except ValueError as e:
        if "missing '='" in str(e):
            print("✓ test_parse_pair_no_equals passed")
            tests_passed += 1
        else:
            print(f"✗ test_parse_pair_no_equals failed: Wrong error message: {e}")
            tests_failed += 1
    
    # Test 6: Complex pairs
    try:
        result = parse_pair('username=john.doe@example.com')
        assert result == ('username', 'john.doe@example.com')
        result = parse_pair('path=/home/user/file.txt')
        assert result == ('path', '/home/user/file.txt')
        print("✓ test_parse_pair_complex passed")
        tests_passed += 1
    except Exception as e:
        print(f"✗ test_parse_pair_complex failed: {e}")
        tests_failed += 1
    
    print("-" * 50)
    print(f"\n{tests_passed} passed, {tests_failed} failed")
    
    if tests_failed == 0:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print(f"\n✗ {tests_failed} test(s) failed")
        sys.exit(1)
        
except ImportError as e:
    print(f"ERROR: Could not import behavior_parser: {e}")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: Unexpected error: {e}")
    sys.exit(1)
