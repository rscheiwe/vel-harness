# Vel Harness Hardening Specification

## Purpose
Harden `vel_harness` behavior and observability based on trace findings:
- Skill registration is overly permissive (`*.md` treated as skills), causing routing noise.
- Event volume is high and redundant for normal operations.
- Agent decisioning is often exploratory/erratic before converging on the correct data path.

This spec defines the target architecture, rollout plan, and acceptance criteria. No implementation is included here.

## Scope
In scope:
- Skills discovery/registry correctness.
- Trace/event model simplification and telemetry modes.
- Runtime decision policy for faster convergence and less tool churn.
- Evaluation framework and release gates.

Out of scope:
- Rewriting model prompts from scratch.
- Domain-specific content changes in Taboola skills.
- Replacing Langfuse.

## Findings (From Observed Runs)
1. Skill misclassification:
- Loader currently scans broad `*.md` and registers many non-skill docs as skills.
- Effect: ambiguous skill list, noisy `list_skills/search_skills`, weak skill identity (e.g., `"Skill"`).

2. Event inflation:
- Each tool call emits multiple events (`assistant-tool-call`, `tool-start`, `tool-success/failure`, `assistant-tool-result`) plus generation slices.
- Effect: very high event counts for routine runs and harder operational debugging.

3. Reasoning inefficiency:
- For operational tasks, agent explores multiple routes before selecting one (e.g., scripts, MCP paths, DB mirrors).
- Effect: high `ls/grep/read_file` + repeated execute attempts before productive query.

## Design Goals
1. Correctness first:
- Register only actual skills as skills.
- Keep supplementary docs as knowledge assets, not skill entries.

2. Operational signal over noise:
- Retain deep debug capability while reducing default event chatter.

3. Faster convergence:
- Make task-type routing explicit and limit exploratory wandering.

4. Safe rollout:
- Mode-based controls, feature flags, and measurable gates.

## Non-Goals
- Eliminating all exploration.
- Enforcing a single global workflow for all tasks.
- Removing detailed tracing entirely.

---

## A. Skills System Hardening

### A1. Skill File Contract
Adopt strict skill-entry contract:
- A skill is either:
  - `SKILL.md` in a skill directory, or
  - markdown with valid frontmatter containing `name` and `description` and `kind: skill`.
- Any other markdown is treated as `knowledge_asset`, not a skill.

### A2. Directory Semantics
Expected skill package layout:
- `SKILL.md` (required entrypoint)
- `recipes/`, `reference/`, `definitions/`, `workflows/`, `confluence/` (knowledge assets)

### A3. Loader Behavior Changes
- Default discovery mode: `entrypoint_only`
  - Load only `**/SKILL.md`.
- Optional compatibility mode: `legacy_markdown_scan` (temporary fallback).
- New metadata on loaded items:
  - `kind`: `skill | knowledge_asset`
  - `source_path`
  - `entrypoint: bool`

### A4. Registry Behavior Changes
- Registry stores two collections:
  - `skills` (activatable)
  - `assets` (reference-only)
- `list_skills()` returns activatable skills only.
- Add `list_skill_assets(skill_name)` to expose related docs.

### A5. Activation Semantics
- `activate_skill(name)` must resolve to a unique `SKILL.md` entrypoint.
- On ambiguity, return deterministic error with candidates.

### A6. Compatibility and Migration
- Feature flags:
  - `VH_SKILLS_ENTRYPOINT_ONLY=1` (default after rollout)
  - `VH_SKILLS_LEGACY_SCAN=0` (off by default after deprecation window)
- Emit startup warning when legacy mode registers >N markdown "skills".

### A7. Acceptance Criteria
- In Taboola plugin directories, only intended skill entrypoints are activatable.
- Confluence/reference markdown files no longer appear in `list_skills()`.
- Existing skill activation by name remains stable or fails with actionable error.

---

## B. Telemetry/Event Model Hardening

### B1. Telemetry Modes
Introduce mode switch:
- `minimal`: run-level summaries only.
- `standard` (default): compact step-level events.
- `debug`: full current verbosity.

### B2. Event Consolidation
In `standard` mode:
- Replace verbose 4-event tool lifecycle with one canonical event:
  - `tool_call_summary`:
    - `tool_name`, `status`, `duration_ms`, `input_fingerprint`, `output_fingerprint`, `error_type`
- Keep `run-start`, `run-end`, `verification` markers.
- Collapse generation fragments into per-step summary:
  - `assistant_step_summary`:
    - `reasoning_phase`, `text_tokens`, `tool_intent`, `step_duration_ms`

### B3. Deduplication/Retry Annotation
- If same tool+input repeats within window, mark as retry:
  - `retry_of_call_id`
  - `retry_reason` (timeout, missing dep, auth, etc.)
- Avoid duplicate full payload emission in standard mode.

### B4. Payload Size Controls
- Hash large inputs/outputs by default in standard mode.
- Store full payloads only in debug mode.

### B5. Langfuse Mapping
- Maintain backward compatibility tags:
  - include `event_version`, `telemetry_mode`.
- Provide normalizer that can read both old and new event schemas.

### B6. Acceptance Criteria
- Standard mode reduces event count by >=50% for representative tasks.
- No loss in ability to identify tool failures/retries.
- Debug mode remains parity-equivalent to current diagnostics.

---

## C. Reasoning/Decision Policy Hardening

### C1. Task Classifier
Add early task classification (`before deep exploration`):
- `data_retrieval` (numeric/time-window KPI)
- `workflow_resolution` (case diagnosis/playbook)
- `code_change`

### C2. Class-Specific Decision Budgets
Example defaults:
- `data_retrieval`:
  - max discovery round: 1
  - expected path: skill -> schema/context -> query -> answer
- `workflow_resolution`:
  - max discovery rounds: 2
  - expected path: skill -> workflow/recipes -> targeted evidence -> resolution

### C3. Mandatory Evidence Gates
- If output includes quantitative claim, query evidence is mandatory.
- If evidence missing:
  - output marked hypothesis/unresolved
  - explicit missing-evidence + next actions

### C4. Exploration Guardrails
- Per-run caps on repeated calls:
  - identical `execute` command repeats
  - repeated `ls/grep/read_file` on same target
- Short-circuit policy:
  - after N low-value exploration calls, require plan commit or fail-fast hint.

### C5. Tool Route Preferences
For known domains (e.g., billing/support analytics):
- prefer canonical data routes first (datastore/query layer) over ad-hoc local scripts, unless explicitly requested.

### C6. Planning/Todo Churn Limits
- Limit todo updates to phase transitions.
- Disallow repetitive micro-updates that do not change plan state.

### C7. Acceptance Criteria
- For `data_retrieval` prompts, median time-to-first-query improves materially.
- Repeated identical command rate drops by >=60%.
- Final answer quality does not regress (same or better correctness).

---

## D. Runtime Controls and Config

### D1. New Config Knobs (Proposed)
- `skills.discovery_mode = entrypoint_only | legacy_markdown_scan`
- `telemetry.mode = minimal | standard | debug`
- `reasoning.max_discovery_rounds_by_class`
- `reasoning.max_repeated_identical_tool_calls`
- `reasoning.max_repeated_identical_execute`
- `reasoning.enforce_query_evidence_for_numeric_claims = true`

### D2. Safety Defaults
- Default to conservative hardening without breaking existing users:
  - entrypoint-only skills (with migration warning fallback)
  - standard telemetry mode
  - moderate discovery caps

---

## E. Evaluation Plan

### E1. Bench Suite
Build fixed benchmark set (at minimum):
- Billing case resolution prompt.
- Billing "recent Salesforce cases" prompt.
- COO analytics revenue query prompt.
- Mixed ambiguous prompt.

### E2. Metrics
- Efficiency:
  - tool calls/run
  - time-to-first-productive-query
  - repeated identical command count
  - exploration/query ratio
- Quality:
  - answer correctness (judge rubric)
  - evidence completeness
  - unresolved correctness when evidence missing
- Telemetry:
  - events/run by mode
  - storage/ingest payload size

### E3. Gates
- Must pass quality parity (no material regression).
- Must meet event reduction target in standard mode.
- Must reduce repeated command/tool loops.

---

## F. Rollout Strategy

### Phase 0: Instrumentation Baseline
- Capture baseline on benchmark suite.

### Phase 1: Skills Contract
- Ship entrypoint-only discovery + assets separation behind flag.
- Validate activation behavior in all existing skill repos.

### Phase 2: Telemetry Standard Mode
- Ship compact schema and compatibility normalizer.
- Keep debug mode as escape hatch.

### Phase 3: Decision Policy
- Ship task classifier + discovery budgets + anti-loop controls.
- Enable numeric-claim evidence gate by default.

### Phase 4: Default Flip
- Switch defaults after gates pass for 2 consecutive runs.

---

## G. Risks and Mitigations

Risk: Breaking legacy skill directories that rely on broad markdown scan.
- Mitigation: temporary legacy mode + migration report listing dropped pseudo-skills.

Risk: Over-constraining exploration harms edge-case accuracy.
- Mitigation: class-based budgets + explicit override path + debug mode.

Risk: Event consolidation hides root-cause details.
- Mitigation: debug mode retains full fidelity and call-level payloads.

---

## H. Implementation Work Items (No Code Yet)

1. Skills loader/registry
- Tighten discovery contract and add asset registry.
- Update middleware tool responses to reflect skill/asset distinction.

2. Telemetry
- Add telemetry mode config and new compact event schema.
- Add compatibility adapter in analysis pipeline.

3. Reasoning
- Add task classifier and discovery budget manager.
- Add repeated-call guards and query-evidence enforcement hooks.

4. Evaluation
- Add benchmark runner and regression dashboard outputs.

---

## I. Definition of Done
- Skill discovery is deterministic and entrypoint-based.
- Standard telemetry is materially smaller and still actionable.
- Data prompts converge quickly to query execution.
- Workflow prompts produce grounded resolutions with explicit evidence policy.
- Benchmark gates are met and documented.
