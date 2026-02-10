---
name: Code Review
description: Guidelines for reviewing code quality, security, and best practices
tags:
  - coding
  - review
  - quality
triggers:
  - review code
  - code review
  - check code
priority: 10
---

# Code Review Skill

When reviewing code, follow these guidelines:

## 1. Correctness
- Does the code do what it's supposed to do?
- Are edge cases handled?
- Are there any logic errors?

## 2. Security
- Check for SQL injection vulnerabilities
- Look for XSS vulnerabilities
- Verify input validation
- Check for hardcoded secrets

## 3. Performance
- Look for N+1 queries
- Check for unnecessary loops
- Identify memory leaks

## 4. Readability
- Are variable names descriptive?
- Is the code well-organized?
- Are comments helpful (not obvious)?

## 5. Testing
- Are there adequate tests?
- Do tests cover edge cases?
- Is test coverage sufficient?

## Response Format

When completing a code review, structure your response as:

```
## Summary
[Brief overview of the code]

## Issues Found
- [ ] Issue 1: Description
- [ ] Issue 2: Description

## Recommendations
1. Recommendation with explanation
2. Recommendation with explanation

## Rating
[Quality score out of 10]
```
