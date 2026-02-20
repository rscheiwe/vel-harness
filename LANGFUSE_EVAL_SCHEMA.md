# Langfuse Eval Schema (Vel Harness)

This file is the source-of-truth checklist for evaluating harness quality in Langfuse without overfitting.

## 1) Datasets

Create these datasets:

- `coding_discipline_v1`
- `parallel_discipline_v1`

## 2) Required Run Metadata

Attach these metadata fields to each trace/run:

- `experiment_id` (string)
- `harness_version` (string, example: `v4`)
- `prompt_pack` (enum: `coding_discipline_v1`, `parallel_discipline_v1`)
- `model` (string)
- `middleware_profile` (string)
- `run_id` (string)
- `session_id` (string)

## 3) Deterministic Per-Run Scores (0/1)

Create these score keys in Langfuse:

- `completed`
- `run_error`
- `timeout`
- `verified`
- `todo_used`
- `parallel_used`
- `followup_reverified`

## 4) Per-Run Aggregate Score

Create:

- `discipline_score` (0-100)

Formula:

1. Start at `100`.
2. Subtract `40` if `completed=0`.
3. Subtract `25` if coding-intent and `verified=0`.
4. Subtract `15` if todo-expected and `todo_used=0`.
5. Subtract `15` if parallel-opportunity and `parallel_used=0`.
6. Subtract `10` if `run_error=1`.
7. Floor at `0`.

## 5) Batch-Level KPI Definitions

Compute these in analysis jobs/dashboard queries:

- `completion_rate = avg(completed)`
- `error_rate = avg(run_error)`
- `timeout_rate = avg(timeout)`
- `verification_compliance_rate = avg(verified on coding-intent runs)`
- `todo_compliance_rate = avg(todo_used on todo-expected runs)`
- `parallel_capture_rate = avg(parallel_used on parallel-opportunity runs)`
- `followup_reverify_rate = avg(followup_reverified on followup runs)`

## 6) Optional LLM-as-Judge (Secondary Only)

Use only for qualitative output quality:

- `output_correctness` (1-5)
- `output_clarity` (1-5)
- `instruction_adherence` (1-5)

Do not gate releases on LLM-as-judge alone.

## 7) Release Gates (Require 2 Consecutive Failing Batches)

Open optimization work only if a threshold is breached in 2 consecutive batches:

- `completion_rate < 0.85`
- `verification_compliance_rate < 0.90` (coding pack)
- `todo_compliance_rate < 0.75` (coding pack)
- `parallel_capture_rate < 0.80` (parallel pack)
- `error_rate > 0.15` or `timeout_rate > 0.10`

## 8) Dashboard Panels

Recommended dashboard views:

1. KPI trends by `harness_version`
2. A/B compare by `experiment_id`
3. Failure slices (`run_error=1`, `timeout=1`, `verified=0`)

## 9) Operating Policy

- Avoid ad-hoc tuning from single-run outcomes.
- Keep deterministic discipline metrics as primary decision signal.
- Use LLM judge for secondary quality interpretation.
- Promote harness changes only when KPI gates indicate persistent degradation.

