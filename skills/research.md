---
name: Research Methodology
description: Systematic approach to investigating topics and synthesizing findings
tags:
  - research
  - investigation
  - synthesis
triggers:
  - research*
  - investigate*
  - study*
  - find information
priority: 15
---

# Research Methodology

When conducting research, follow this systematic methodology:

## 1. Define the Research Question

Before starting research:

- Clearly state what you're trying to find out
- Break complex topics into specific sub-questions
- Identify what constitutes a complete answer
- Set scope boundaries

## 2. Identify Information Sources

Consider multiple source types:

- Primary sources (original documents, data)
- Secondary sources (analyses, summaries)
- Expert opinions and documentation
- Code and implementation details

## 3. Gather Information Systematically

For comprehensive research:

- Use `spawn_parallel()` for independent sub-topics
- Search files with `grep()` for relevant code/docs
- Read files with `read_file()` for detailed analysis
- Take notes on key findings

## 4. Parallel Research Pattern

When topics can be researched independently:

```
1. Identify 3-5 independent aspects to investigate
2. Spawn parallel subagents for each aspect
3. Wait for all results
4. Synthesize findings
```

Example:
```
subagents = await spawn_parallel([
    "Research the authentication system",
    "Research the database schema",
    "Research the API endpoints",
])
results = await wait_all_subagents()
```

## 5. Verify and Cross-Reference

Always verify findings:

- Check multiple sources when possible
- Look for contradictions or inconsistencies
- Validate technical claims against code
- Note confidence levels for claims

## 6. Synthesize Findings

Combine research into coherent output:

- Organize by theme or question
- Connect related findings
- Highlight key insights
- Note gaps in information

## 7. Document Sources

Maintain traceability:

- Note which files contain relevant info
- Record line numbers for specific claims
- Distinguish facts from interpretations
- Flag areas of uncertainty

## Best Practices

- Start broad, then focus on important areas
- Use parallel research for efficiency
- Verify critical information
- Organize findings logically
- Be explicit about what's unknown
