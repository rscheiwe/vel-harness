# vel_harness-ts Parity Assessment (vs Python vel_harness)

Date: 2026-02-20

This document estimates how much work is required to bring `vel_harness-ts` to practical parity with the Python harness.

## Executive Summary

`vel_harness-ts` currently covers a useful core:
- filesystem tools
- planning tools
- skills loading/activation
- subagent spawning/waiting
- basic harness orchestration

But Python `vel_harness` has a much larger reliability and operations stack (verification, tracing/Langfuse, run guard, time budgets, local context, loop detection, retry/caching, memory, reasoning scheduler, analysis/eval tooling).

Bottom line:
- Core runtime parity: **partial**
- Reliability parity: **low**
- Eval/ops parity: **low**
- Test parity: **very low**

Estimated effort to reach strong parity:
- **1 engineer**: ~7-9 weeks
- **2 engineers**: ~3-5 weeks

## Evidence Snapshot

Python harness enables many middleware controls by default:
- `vel_harness/harness.py:251`
- `vel_harness/harness.py:274`
- `vel_harness/harness.py:279`
- `vel_harness/harness.py:291`

Python factory wires advanced middleware:
- `vel_harness/factory.py:1084`
- `vel_harness/factory.py:1095`
- `vel_harness/factory.py:1104`
- `vel_harness/factory.py:1113`
- `vel_harness/factory.py:1121`
- `vel_harness/factory.py:1130`

TS harness currently registers only 4 middleware types:
- `vel_harness-ts/src/harness.ts:101`
- `vel_harness-ts/src/harness.ts:109`
- `vel_harness-ts/src/harness.ts:114`
- `vel_harness-ts/src/harness.ts:123`

TS middleware exports are limited to:
- `vel_harness-ts/src/middleware/index.ts:5`
- `vel_harness-ts/src/middleware/index.ts:9`

TS config includes fields that are not currently wired into runtime middleware:
- `vel_harness-ts/src/types/config.ts:30`
- `vel_harness-ts/src/types/config.ts:34`
- `vel_harness-ts/src/types/config.ts:39`

Python has one-call role workflow helper; TS subagent middleware does not currently expose equivalent tool:
- Python helper: `vel_harness/harness.py:539`
- Python tool: `vel_harness/middleware/subagents.py:181`
- TS subagent tool list ends without workflow tool: `vel_harness-ts/src/middleware/subagents.ts:267`

Test coverage gap is large:
- Python test files: 37
- TS test files: 1

## Parity Matrix

### 1) Core Harness API
- `run` / `runStream`: **TS present**
- agent registry + custom agents: **TS present**
- subagent event listener: **TS present**
- session abstraction (`HarnessSession`): **Python only**
- fallback model wrapper / retries: **Python only**

Assessment: **Partial parity**

### 2) Middleware Coverage
- Filesystem: **both**
- Planning: **both**
- Skills: **both**
- Subagents: **both (but TS lacks workflow helper tool)**
- Local context onboarding: **Python only**
- Loop detection: **Python only**
- Verification middleware: **Python only**
- Tracing middleware + Langfuse emit: **Python only**
- Time budget middleware: **Python only**
- Run guard middleware: **Python only**
- Retry middleware: **Python only**
- Caching middleware: **Python only**
- Memory middleware: **Python only**
- Sandbox middleware: **Python only**
- Database middleware: **Python only**
- Context management middleware: **Python only**

Assessment: **Major gap**

### 3) Reliability/Guardrail Behavior
- deterministic completion gating (`require_verification_before_done`): **Python only**
- tool budgets and repeat/failure caps: **Python only**
- long-loop mitigation hooks: **Python only**
- phase-aware reasoning budgets: **Python only**

Assessment: **Major gap**

### 4) Observability + Eval Tooling
- trace analysis taxonomy: **Python only** (`vel_harness/analysis/*`)
- experiment compare/cycle scripts: **Python only** (`scripts/*`)
- Langfuse loader + normalization: **Python only**

Assessment: **Major gap**

### 5) Test/Quality Infrastructure
- Python has broad unit/integration coverage across runtime/middleware/analysis.
- TS currently validates mostly skills loader/registry behavior.

Assessment: **Major gap**

## Work Breakdown (Estimated)

## Phase A: Foundation + Config Truthfulness (4-6 days)
- Wire `HarnessConfig` flags to real behavior or remove misleading fields.
- Add missing middleware plumbing interfaces in TS harness (enable/disable by config).
- Add minimal parity test harness scaffolding.

Deliverable: TS config accurately reflects runtime behavior.

## Phase B: Reliability Middleware Parity (12-16 days)
- Implement TS equivalents:
  - local_context
  - loop_detection
  - verification
  - time_budget
  - run_guard
  - tracing (event model similar to Python)
- Add `run_subagent_workflow` helper tool parity in TS subagents middleware.

Deliverable: TS runtime has comparable discipline controls.

## Phase C: Execution/Data Capabilities (8-12 days)
- Sandbox middleware/backend parity for `execute`/`execute_python`.
- Database middleware parity (if required in TS use cases).
- Memory + context management parity.

Deliverable: TS can run coding/research workflows with similar operational guarantees.

## Phase D: Eval + Experiment Tooling (6-9 days)
- Port/implement:
  - trace analysis taxonomy
  - experiment comparison and cycle reporting
  - Langfuse fetch/normalization adapters

Deliverable: TS can be improved with the same outer-loop methodology as Python.

## Phase E: Test Suite + Docs (8-12 days)
- Expand TS tests to cover middleware and failure modes.
- Add parity regression tests:
  - verification gating
  - todo discipline
  - parallel capture
  - long-loop interruption
- Document TS operations runbook similar to `docs/HARNESS_OPERATIONS.md`.

Deliverable: confidence for production use and regression prevention.

## Total Effort
- ~38 to 55 engineer-days depending on depth and polish.

## Recommended Scope Strategy (Judicious)

Avoid "full parity everywhere" up front. Use staged parity targets:

1. **Operational parity first** (B + parts of D): verification, run guard, tracing.
2. **Then execution/data parity** (C): sandbox/database/memory as needed.
3. **Then full eval/testing parity** (rest of D/E).

This aligns work with real reliability outcomes and avoids over-building.

## Do We Need vel-ts Changes?

Likely **minimal to moderate**, not primary:
- `vel-ts` already exposes hooks/tool lifecycle events, which should support tracing/run-guard style middleware.
- Most parity work appears harness-layer in `vel_harness-ts`.
- Reassess after implementing TS tracing + run_guard prototype; only escalate to `vel-ts` if required events/controls are missing.

