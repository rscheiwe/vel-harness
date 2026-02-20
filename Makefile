PYTHON ?= python

.PHONY: smoke compile analyze-traces compare-experiments experiment-cycle

smoke:
	$(PYTHON) scripts/smoke_harness.py

compile:
	$(PYTHON) -m compileall -q vel_harness tests examples scripts

# Usage:
# make analyze-traces INPUT=traces.json
# make analyze-traces LANGFUSE=1 LIMIT=50 OUTPUT=analysis.json
analyze-traces:
	$(PYTHON) scripts/analyze_traces.py \
	$$( [ -n "$(INPUT)" ] && echo --input "$(INPUT)" ) \
	$$( [ -n "$(LANGFUSE)" ] && echo --langfuse ) \
	$$( [ -n "$(LIMIT)" ] && echo --limit "$(LIMIT)" ) \
	$$( [ -n "$(OUTPUT)" ] && echo --output "$(OUTPUT)" )

# Usage:
# make compare-experiments BASELINE=baseline_analysis.json CANDIDATE=candidate_analysis.json OUTPUT=comparison.json
compare-experiments:
	$(PYTHON) scripts/compare_experiments.py \
	--baseline "$(BASELINE)" \
	--candidate "$(CANDIDATE)" \
	$$( [ -n "$(OUTPUT)" ] && echo --output "$(OUTPUT)" )

# Usage:
# make experiment-cycle BASELINE=baseline.json CANDIDATE=candidate.json OUT_JSON=cycle.json OUT_MD=cycle.md
experiment-cycle:
	$(PYTHON) scripts/run_experiment_cycle.py \
	$$( [ -n "$(BASELINE)" ] && echo --baseline "$(BASELINE)" ) \
	$$( [ -n "$(CANDIDATE)" ] && echo --candidate "$(CANDIDATE)" ) \
	$$( [ -n "$(LANGFUSE_BASELINE)" ] && echo --langfuse-baseline ) \
	$$( [ -n "$(LANGFUSE_CANDIDATE)" ] && echo --langfuse-candidate ) \
	$$( [ -n "$(LIMIT)" ] && echo --limit "$(LIMIT)" ) \
	$$( [ -n "$(OUT_JSON)" ] && echo --out-json "$(OUT_JSON)" ) \
	$$( [ -n "$(OUT_MD)" ] && echo --out-md "$(OUT_MD)" )
