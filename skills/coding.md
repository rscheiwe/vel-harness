---
name: Coding Best Practices
description: Guidelines for writing, testing, and debugging code
tags:
  - coding
  - development
  - testing
  - debugging
triggers:
  - write code
  - implement*
  - create function
  - fix bug
  - debug*
priority: 10
---

# Coding Best Practices

When writing or modifying code, follow these practices:

## 1. Plan Before Coding

Before writing code:

- Use `write_todos()` to plan the implementation
- Break down into small, testable steps
- Consider edge cases upfront
- Think about error handling

## 2. Read Existing Code First

Before modifying code:

- Use `read_file()` to understand the context
- Check for existing patterns and conventions
- Look for related implementations
- Understand dependencies

## 3. Write Clean Code

Follow these principles:

- Use descriptive variable and function names
- Keep functions small and focused
- Add comments for complex logic
- Follow the project's style conventions

Example structure:
```python
def calculate_total(items: List[Item], discount: float = 0.0) -> float:
    """
    Calculate the total price for a list of items.

    Args:
        items: List of items to calculate
        discount: Percentage discount to apply (0.0 to 1.0)

    Returns:
        Total price after discount
    """
    subtotal = sum(item.price * item.quantity for item in items)
    return subtotal * (1 - discount)
```

## 4. Test Your Code

Always test implementations:

```python
# Use execute_python() to test
code = '''
def add(a, b):
    return a + b

# Test cases
assert add(2, 3) == 5
assert add(-1, 1) == 0
assert add(0, 0) == 0
print("All tests passed!")
'''
```

## 5. Debug Systematically

When debugging:

1. Reproduce the issue
2. Add diagnostic output
3. Narrow down the cause
4. Fix and verify
5. Check for similar issues

## 6. Handle Errors Gracefully

Include appropriate error handling:

```python
try:
    result = process_data(input_data)
except ValueError as e:
    logger.error(f"Invalid input: {e}")
    raise
except IOError as e:
    logger.error(f"IO error: {e}")
    return None
```

## 7. Document Changes

When modifying code:

- Update any affected comments
- Update function docstrings if behavior changes
- Note breaking changes
- Update tests as needed

## Best Practices

- Write code that's easy to read
- Test edge cases and error conditions
- Use version control effectively
- Keep changes focused and atomic
- Refactor when code becomes complex
