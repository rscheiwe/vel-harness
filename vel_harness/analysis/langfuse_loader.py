"""Langfuse trace loading helpers with tolerant schema handling."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List


def fetch_langfuse_traces(limit: int = 100) -> List[Dict[str, Any]]:
    """Fetch traces from Langfuse client across common SDK shapes."""
    try:
        from langfuse import Langfuse
    except Exception as e:
        raise RuntimeError("langfuse package unavailable; install langfuse to fetch traces") from e

    host = os.environ.get("LANGFUSE_HOST") or os.environ.get("LANGFUSE_BASE_URL")
    timeout = int(os.environ.get("LANGFUSE_TIMEOUT_SECONDS", "30"))
    client = Langfuse(host=host, timeout=timeout)

    # Intermittent list/read timeouts happen in cloud environments.
    # Retry quickly a few times before surfacing the failure.
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            traces: List[Dict[str, Any]] = []

            # Shape A
            fetch_traces = getattr(client, "fetch_traces", None)
            if callable(fetch_traces):
                result = fetch_traces(limit=limit)
                data = getattr(result, "data", result)
                traces = _coerce_list(data)
                return _attach_observations_if_available(client, traces, limit)

            # Shape B
            api = getattr(client, "api", None)
            if api is not None and hasattr(api, "trace") and hasattr(api.trace, "list"):
                result = api.trace.list(limit=limit)
                data = getattr(result, "data", result)
                traces = _coerce_list(data)
                return _attach_observations_if_available(client, traces, limit)

            raise RuntimeError("Unsupported Langfuse SDK shape")
        except Exception as e:
            last_error = e
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            break

    raise RuntimeError(f"Failed to fetch Langfuse traces after retries: {last_error}") from last_error


def _attach_observations_if_available(client: Any, traces: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    """Attach observation arrays to trace objects when available.

    Langfuse trace.list responses commonly omit nested observations.
    We fetch observations separately and group by trace_id so downstream
    normalization can produce event streams.
    """
    api = getattr(client, "api", None)
    if api is None or not hasattr(api, "observations"):
        return traces
    obs_client = getattr(api, "observations", None)
    get_many = getattr(obs_client, "get_many", None)
    if not callable(get_many):
        return traces

    # Pull enough rows to cover recent traces. Keep bounded for safety.
    obs_limit = max(limit * 20, 20)
    obs_limit = min(obs_limit, 100)
    try:
        obs_result = get_many(limit=obs_limit)
    except Exception:
        return traces
    raw_obs = getattr(obs_result, "data", obs_result)
    observations = _coerce_list(raw_obs)
    if not observations:
        return traces

    by_trace: Dict[str, List[Dict[str, Any]]] = {}
    for obs in observations:
        trace_id = str(obs.get("trace_id") or obs.get("traceId") or "")
        if not trace_id:
            continue
        by_trace.setdefault(trace_id, []).append(obs)

    if traces:
        out: List[Dict[str, Any]] = []
        for trace in traces:
            tid = str(trace.get("id", ""))
            merged = dict(trace)
            if tid and tid in by_trace:
                merged["observations"] = by_trace[tid]
            out.append(merged)
        return out

    # Fallback when trace list is empty but observations exist:
    # build synthetic trace shells keyed by trace_id.
    synthetic: List[Dict[str, Any]] = []
    for tid, obs_list in by_trace.items():
        synthetic.append({"id": tid, "observations": obs_list})
    return synthetic[:limit]


def normalize_trace_object(trace: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a Langfuse trace object to include `events` list when possible."""
    def _s(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    if "events" in trace and isinstance(trace["events"], list):
        return trace

    # Try observations -> events
    obs = trace.get("observations")
    if isinstance(obs, list):
        events = []
        seq = 0
        inferred_session_id = _s(trace.get("sessionId", trace.get("session_id", "")))
        for item in obs:
            if not isinstance(item, dict):
                continue
            seq += 1
            name = item.get("name") or item.get("type") or "observation"
            input_payload = item.get("input")
            output_payload = item.get("output")
            level = item.get("level") or ""
            ev_type = "observation"
            lname = str(name).lower()
            if "tool" in lname and level == "ERROR":
                ev_type = "tool-failure"
            elif "tool" in lname:
                ev_type = "tool-success"
            elif "verification" in lname:
                ev_type = "verification-followup-required"
            metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
            if not inferred_session_id and metadata.get("session_id"):
                inferred_session_id = _s(metadata.get("session_id"))
            events.append(
                {
                    "seq": seq,
                    "event_type": ev_type,
                    "run_id": _s(trace.get("id", "")),
                    "session_id": inferred_session_id,
                    "data": {
                        "name": name,
                        "input": input_payload,
                        "output": output_payload,
                        "error": item.get("statusMessage") or item.get("error"),
                    },
                }
            )
        if events:
            normalized = dict(trace)
            normalized["events"] = events
            return normalized

    return trace


def _coerce_list(items: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return out
    for item in items:
        if isinstance(item, dict):
            out.append(item)
            continue
        if hasattr(item, "__dict__"):
            out.append(dict(item.__dict__))
    return out
