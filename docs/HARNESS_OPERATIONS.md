# Harness Operations Guide

This document is the operational reference for running, validating, and improving `vel_harness`.

## 1) Baseline Dev Commands

```bash
# quick sanity
make smoke

# compile checks
make compile

# full tests
python -m pytest -q
```

If your local environment has pytest capture issues, use:

```bash
python -m pytest -p no:capture -q
```

## 2) Recommended Stable Python Environment

```bash
/opt/homebrew/bin/python3.11 -m venv .venv311
.venv311/bin/python -m pip install pytest pytest-asyncio pytest-mock anyio pytest-cov
.venv311/bin/python -m pip install httpx pydantic jsonschema python-dotenv tenacity jinja2 openai google-generativeai anthropic pyyaml textual click rich
PYTHONPATH=/Users/richard.s/vel .venv311/bin/python -m pytest -q
```

## 3) Strengthened Runtime Defaults (Current)

`VelHarness` defaults now include:
- `local_context` onboarding
- `loop_detection` hints
- `verification` pre-completion follow-up
- `tracing` event recording (Langfuse emission if configured)
- `reasoning_scheduler` (phase-aware native reasoning budget)
- `run_guard` deterministic hard limits (tool budgets, repeat/failure caps, subagent caps, completion gating)

## 4) Trace Analysis Workflow

### Langfuse Environment (required for `--langfuse`)

Set these in your root `.env` (or shell env):

```bash
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_HOST=https://us.cloud.langfuse.com
```

Optional:

```bash
LANGFUSE_TIMEOUT_SECONDS=45
```

Notes:
- Use `LANGFUSE_HOST` (preferred). `LANGFUSE_BASE_URL` is also accepted as fallback.
- For short-lived scripts, tracing now flushes Langfuse on run end to avoid dropped events.

### Langfuse Bring-Up Checks

1) Verify fetch path:

```bash
python scripts/analyze_traces.py --langfuse --limit 1 --output /tmp/lf_probe.json
```

2) Emit one real run:

```bash
python examples/export_trace_run.py --out /tmp/lf_emit.json --session-id lf-emit-01
```

3) Re-fetch and confirm `runs_analyzed > 0`:

```bash
python scripts/analyze_traces.py --langfuse --limit 5 --output /tmp/lf_after_emit.json
```

If fetch succeeds but `runs_analyzed` is 0:
- ensure a real emit run was executed recently,
- increase `LANGFUSE_TIMEOUT_SECONDS`,
- re-run with small `--limit` first (e.g. 1-5).

### Analyze trace export JSON

```bash
python scripts/analyze_traces.py --input traces.json
```

### Analyze using Langfuse SDK

```bash
python scripts/analyze_traces.py --langfuse --limit 50 --output analysis.json
```

### Makefile shortcuts

```bash
make analyze-traces INPUT=traces.json OUTPUT=analysis.json
make analyze-traces LANGFUSE=1 LIMIT=50 OUTPUT=analysis.json
```

## 5) Compare Experiments (Regression/Uplift)

Inputs can be:
- analysis outputs from `analyze_traces.py`, or
- raw trace JSON exports.

```bash
python scripts/compare_experiments.py \
  --baseline baseline_analysis.json \
  --candidate candidate_analysis.json \
  --output comparison.json
```

Makefile shortcut:

```bash
make compare-experiments BASELINE=baseline_analysis.json CANDIDATE=candidate_analysis.json OUTPUT=comparison.json
```

## 6) Full Experiment Cycle (Baseline + Candidate + Report)

Run a complete loop and emit JSON + Markdown:

```bash
python scripts/run_experiment_cycle.py \
  --baseline baseline_traces.json \
  --candidate candidate_traces.json \
  --out-json cycle.json \
  --out-md cycle.md
```

Makefile shortcut:

```bash
make experiment-cycle BASELINE=baseline_traces.json CANDIDATE=candidate_traces.json OUT_JSON=cycle.json OUT_MD=cycle.md
```

Langfuse-driven run:

```bash
make experiment-cycle LANGFUSE_BASELINE=1 LANGFUSE_CANDIDATE=1 LIMIT=100 OUT_JSON=cycle.json OUT_MD=cycle.md
```

## 6.1) Reproducible Experiment Wrapper ("Lab Notebook")

Use this when you want a single command that captures exactly what produced a result:
- model/provider
- harness config + middleware toggles
- prompt snapshot + hash
- optional analysis and baseline comparison

```bash
python scripts/run_harness_experiment.py \
  --name hardening-v1 \
  --output-dir .experiments \
  --provider anthropic \
  --model claude-sonnet-4-5-20250929 \
  --trace-input traces.json \
  --baseline-analysis baseline_analysis.json
```

Langfuse variant:

```bash
python scripts/run_harness_experiment.py \
  --name hardening-v1 \
  --output-dir .experiments \
  --langfuse \
  --limit 100
```

Output bundle includes:
- `manifest.json`
- `harness_snapshot.json`
- `prompt.txt`
- `analysis.json` (if traces provided)
- `comparison.json` (if baseline provided)

## 6.2) Behavior-Focused Eval Slice (Todo / Parallel / Verification)

Use a targeted prompt pack when you specifically want to measure:
- todo discipline (`write_todos` / `read_todos`)
- parallel orchestration (`spawn_parallel`)
- verification discipline on coding-intent runs

Suggested flow:

```bash
# 1) run real prompts and export traces (outside sandbox/network-restricted envs if needed)
python examples/export_trace_run.py --sandbox --out tmp/behavior_manual/01_trace.json --session-id behavior-manual-01 --prompt "..." --stream-log tmp/behavior_manual/01_stream.ndjson
python examples/export_trace_run.py --sandbox --out tmp/behavior_manual/02_trace.json --session-id behavior-manual-02 --prompt "..." --stream-log tmp/behavior_manual/02_stream.ndjson
python examples/export_trace_run.py --sandbox --out tmp/behavior_manual/03_trace.json --session-id behavior-manual-03 --prompt "..." --stream-log tmp/behavior_manual/03_stream.ndjson

# 2) merge traces
python - << 'PY'
import json,glob
traces=[]
for p in sorted(glob.glob('tmp/behavior_manual/*_trace.json')):
    traces.extend(json.load(open(p)).get('traces',[]))
json.dump({'traces': traces}, open('tmp/behavior_manual/behavior_manual_traces.json','w'), indent=2)
print('wrote tmp/behavior_manual/behavior_manual_traces.json')
PY

# 3) analyze
python scripts/analyze_traces.py \
  --input tmp/behavior_manual/behavior_manual_traces.json \
  --output tmp/behavior_manual/behavior_manual_analysis.json
```

Important:
- For coding-intent evals, run with sandbox enabled (`--sandbox` or `--sandbox=true`) so `execute`/`execute_python` tools are actually available.
- If sandbox is disabled, verification metrics can be false negatives because the model may correctly report that command execution is unavailable.

Interpretation notes:
- If `coding_intent=true` and `verification_compliance_rate=0`, prioritize stronger verification enforcement.
- If `parallel_opportunity_runs>0` but `parallel_capture_rate=0`, improve prompts/middleware for parallel capture.
- If `todo_expected_runs>0` but `todo_compliance_rate=0`, tighten planning guidance or add stronger todo nudges.

### Parallel-Focused Eval Pack

Use a dedicated prompt pack when you want reliable `parallel_opportunity_runs` and `parallel_capture_rate` signals:

```bash
# prompts file
cat > tmp/eval_prompts_parallel_06.json <<'JSON'
[
  "Use spawn_parallel with exactly 2 tasks: one task inspects vel_harness/middleware/run_guard.py, the other inspects vel_harness/middleware/verification.py. Then merge findings in 4 bullets.",
  "Spawn two subagents in parallel to review docs/HARNESS_OPERATIONS.md and README.md for verification guidance; return overlaps and differences.",
  "Run parallel exploration: Task A find loop detection controls in vel_harness/middleware/loop_detection.py, Task B find time budget controls in vel_harness/middleware/time_budget.py. Then synthesize a short recommendation.",
  "Use spawn_parallel with at least 3 tasks to inspect planning.py, subagents.py, and run_guard.py middleware, then provide a merged summary with one risk per file.",
  "Use run_subagent_workflow with roles discover, implement, verify to propose one concrete reliability improvement and one caveat.",
  "For this prompt, do NOT use parallel/subagents. Read docs/HARNESS_OPERATIONS.md directly and summarize 3 verification commands."
]
JSON

# run per-prompt exports (sandbox enabled)
python examples/export_trace_run.py --sandbox --out tmp/parallel_eval/01_trace.json --session-id parallel-v1-01 --prompt "..."
# repeat for all prompts, then merge
python - << 'PY'
import glob, json
traces = []
for p in sorted(glob.glob('tmp/parallel_eval/*_trace.json')):
    traces.extend(json.load(open(p)).get('traces', []))
json.dump({'traces': traces}, open('tmp/parallel_eval/parallel_traces.json', 'w'), indent=2)
print('wrote tmp/parallel_eval/parallel_traces.json')
PY

# analyze
python scripts/analyze_traces.py --input tmp/parallel_eval/parallel_traces.json --output tmp/parallel_eval/parallel_analysis.json
```

Note:
- Analyzer parallel-opportunity detection now treats explicit `spawn_parallel` multi-task calls as opportunities (not only repeated `spawn_subagent` patterns).
- Coding-intent detection now ignores read-only shell probes (`pwd`, `ls`, `cat`, `grep`, `find`, etc.) so non-coding prompts are less likely to be mislabeled as verification/todo misses.

## 7) Interpreting Failure Taxonomy

The analyzer currently classifies:
- `no_verification`
- `tool_misuse_or_instability`
- `looping_or_doom_edits`
- `timeout_budget_miss`
- `premature_completion`
- `recovery_failure_after_error`

Use top regressions from comparison reports to prioritize next harness changes.

## 7.1) Behavioral Discipline Metrics

In addition to failure taxonomy, analysis now computes behavior metrics per run and in summary:
- `avg_behavior_score` (0-100)
- `todo_compliance_rate` (when todos are expected on complex coding tasks)
- `parallel_capture_rate` (when parallel subagent usage is expected)
- `verification_compliance_rate` (coding-intent runs with verification evidence)
- `followup_reverify_rate` (runs that re-verify after verification followup was required)

This is the primary way to evaluate:
- whether `write_todos` is used when it should be,
- whether `spawn_parallel` is used when opportunities exist,
- and whether verification discipline is consistently followed.

## 8) Runtime Strengthening Controls

Config blocks now available:
- `local_context`
- `loop_detection`
- `verification`
- `tracing`
- `reasoning_scheduler`
- `time_budget`
- `run_guard`

Defaults are clean-sweep hardened for `VelHarness`.

### Current enforcement additions (post-baseline hardening)

- Planning nudge injection (`planning-todo-hint` trace event):
  - For coding/multi-step/delegation prompts with no active todo list, harness injects a deterministic hint to call `write_todos` early.
- Subagent guidance tightening:
  - Prompt/tool descriptions now explicitly prefer `spawn_parallel` when there are 2+ independent delegations.
- Verification signal expansion:
  - Verification detection now counts test and compile/lint evidence (`pytest`, `py_compile`, `make compile`, `ruff check`, `mypy`, etc.).
- RunGuard follow-up strictness:
  - Coding-intent runs without verification evidence now trigger follow-up regardless of completion wording.
- Verification retries:
  - Default `max_followups` increased to `2` (`VerificationConfig`, `VelHarness` defaults).

## 8.1) RunGuard (Hard Runtime Enforcement)

`run_guard` is the deterministic safety layer to prevent long loops and runaway calls:
- tool-call budget cap (`max_tool_calls_total`)
- per-tool caps (`max_tool_calls_per_tool`)
- repeated identical call cap (`max_same_tool_input_repeats`)
- failure streak cap (`max_failure_streak`)
- subagent round cap (`max_subagent_rounds`)
- parallel subagent cap (`max_parallel_subagents`)
- completion gate requiring verification evidence (`require_verification_before_done`)
- optional completion contract checks (`completion_required_paths`, `completion_required_patterns`)

This maps to the middleware-heavy hardening goals:
- `ToolCallBudgetMiddleware` behavior: via `max_tool_calls_total` + `max_tool_calls_per_tool`
- `NoProgressMiddleware` behavior: via repeat/failure streak caps
- `SubagentDelegationPolicyMiddleware` behavior: via subagent round/parallel caps
- `PreCompletionChecklistMiddleware` + `CompletionContractMiddleware` behavior: via verification and completion checks

### Latest behavior-eval snapshot

Artifacts:
- `tmp/behavior_manual/behavior_manual_analysis.json` (baseline slice)
- `tmp/behavior_v2/behavior_v2_analysis.json` (post-hardening slice)
- `tmp/behavior_v2/behavior_compare_manual_to_v2.json` (comparison)

Observed delta on the sampled slice:
- verdict: `improved`
- total failure delta: `-1`
- `premature_completion` reduced
- `no_verification` unchanged in coding-intent runs
- `todo_compliance_rate` / `parallel_capture_rate` / `verification_compliance_rate` still low in coding-intent runs

Interpretation:
- Hardening reduced one completion-gating failure mode.
- Additional prompt/middleware pressure is still needed to consistently force:
  - todo lifecycle usage on coding runs,
  - parallel batching when delegation opportunities exist,
  - explicit verification commands before finalization.

## 9) API/Examples Quick Links

- API examples: `examples/api/`
- End-to-end feature exercise: `examples/test_all_features.py`
- Advanced features server example: `examples/api/advanced_features.py`

## 10) One-Call Multi-Subagent Workflow

Role pipeline available now:
- `discover` -> `implement` -> `verify` -> optional `critic`

Programmatic call:

```python
result = await harness.run_role_workflow(
    goal="Add robust retry handling for network failures",
    session_id="exp-123",
    include_critic=True,
)
```

Session call:

```python
async with harness.create_session("exp-123") as session:
    result = await session.run_role_workflow(
        goal="Add robust retry handling for network failures",
        include_critic=True,
    )
```

Agent tool call (inside runs):
- `run_subagent_workflow(goal, include_critic=True)`
