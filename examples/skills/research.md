---
name: Research Methodology
description: Systematic approach to investigating topics and gathering information
tags:
  - research
  - investigation
  - analysis
triggers:
  - research*
  - investigate*
  - find information
  - gather data
priority: 15
---

# Research Methodology Skill

When conducting research, follow this structured approach:

## Phase 1: Scoping
1. Define the research question clearly
2. Identify what you already know
3. List what you need to find out
4. Set boundaries for the investigation

## Phase 2: Information Gathering
1. Use parallel subagents for independent searches
2. Explore multiple sources
3. Take structured notes
4. Track sources for citation

## Phase 3: Analysis
1. Cross-reference findings
2. Identify patterns and themes
3. Note contradictions
4. Synthesize insights

## Phase 4: Reporting
1. Summarize key findings
2. Provide evidence/sources
3. Highlight uncertainties
4. Suggest next steps

## Using Subagents

When research requires multiple parallel investigations:

```
spawn_subagent(
    task="Research [specific topic] and return key findings",
    agent="explore"
)
```

Wait for results and synthesize before continuing.

## Output Format

```markdown
# Research Report: [Topic]

## Executive Summary
[2-3 sentence overview]

## Key Findings
1. Finding with supporting evidence
2. Finding with supporting evidence

## Sources
- Source 1
- Source 2

## Gaps & Uncertainties
- What remains unknown

## Recommendations
- Next steps
```
