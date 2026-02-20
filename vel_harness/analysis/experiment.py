"""Experiment snapshot and bundle utilities."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def build_harness_snapshot(harness: Any) -> Dict[str, Any]:
    """Build reproducibility snapshot from a VelHarness instance."""
    system_prompt = harness.deep_agent.get_system_prompt()
    prompt_sha = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()
    cfg = harness.config.to_dict()
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "model": harness.model,
        "harness_config": cfg,
        "middleware_names": sorted(list(harness.deep_agent.middlewares.keys())),
        "system_prompt_sha256": prompt_sha,
        "system_prompt_length": len(system_prompt),
    }


def write_experiment_bundle(
    output_dir: str,
    name: str,
    snapshot: Dict[str, Any],
    prompt_text: str,
    analysis_payload: Optional[Dict[str, Any]] = None,
    comparison_payload: Optional[Dict[str, Any]] = None,
) -> str:
    """Write experiment artifact bundle and return directory path."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    root = Path(output_dir).expanduser().resolve() / f"{name}_{ts}"
    root.mkdir(parents=True, exist_ok=True)

    (root / "manifest.json").write_text(
        json.dumps(
            {
                "name": name,
                "captured_at": snapshot.get("captured_at"),
                "model": snapshot.get("model"),
                "system_prompt_sha256": snapshot.get("system_prompt_sha256"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    (root / "harness_snapshot.json").write_text(json.dumps(snapshot, indent=2, sort_keys=True))
    (root / "system_prompt.txt").write_text(prompt_text)
    if analysis_payload is not None:
        (root / "analysis.json").write_text(json.dumps(analysis_payload, indent=2, sort_keys=True))
    if comparison_payload is not None:
        (root / "comparison.json").write_text(json.dumps(comparison_payload, indent=2, sort_keys=True))

    return str(root)

