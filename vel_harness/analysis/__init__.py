"""Trace analysis and failure taxonomy utilities."""

from vel_harness.analysis.trace_analysis import (
    FailureCategory,
    FailureFinding,
    TraceAnalysisReport,
    classify_trace_failures,
    summarize_reports,
)
from vel_harness.analysis.pipeline import (
    extract_event_stream,
    analyze_trace_objects,
    normalize_event_schema,
)
from vel_harness.analysis.compare import (
    compare_analysis_payloads,
)
from vel_harness.analysis.langfuse_loader import (
    fetch_langfuse_traces,
    normalize_trace_object,
)
from vel_harness.analysis.experiment import (
    build_harness_snapshot,
    write_experiment_bundle,
)
from vel_harness.analysis.gates import (
    GateThresholds,
    evaluate_hardening_gates,
    update_default_flip_readiness,
)

__all__ = [
    "FailureCategory",
    "FailureFinding",
    "TraceAnalysisReport",
    "classify_trace_failures",
    "summarize_reports",
    "extract_event_stream",
    "analyze_trace_objects",
    "normalize_event_schema",
    "compare_analysis_payloads",
    "fetch_langfuse_traces",
    "normalize_trace_object",
    "build_harness_snapshot",
    "write_experiment_bundle",
    "GateThresholds",
    "evaluate_hardening_gates",
    "update_default_flip_readiness",
]
