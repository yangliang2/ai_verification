"""Generate local recording fixtures, then invoke only the execute-family CLI.

Run from the repository root with PYTHONPATH=. .venv/bin/python. The preparation helper uses
explicit test APK bytes and simulated source/build receipts, never a host build.
The output directory must not exist; no evidence is overwritten or retried.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from aiverify.bench import runtime_mapping
from tests.bench.test_runtime_family_execution import CANDIDATE, _prepared


root = Path(__file__).resolve().parent
artifacts = root / "recording"
artifacts.mkdir(exist_ok=False)
with pytest.MonkeyPatch.context() as patch:
    predecessor = _prepared(artifacts, patch)
config = artifacts / "opaque-observations.json"
config.write_text(json.dumps({
    "schema_version": 1,
    "evidence_class": "recorded_simulation",
    "lanes": [
        {"lane_id": lane, "observations": {"save_enabled": index % 2 == 0}}
        for index, lane in enumerate(runtime_mapping.FROZEN_LANE_ORDER)
    ],
}, indent=2) + "\n")
command = [
    sys.executable, "-m", "aiverify.bench.runtime_calibration", "execute-family",
    "--candidate-root", str(CANDIDATE),
    "--predecessor-root", str(predecessor),
    "--output-root", str(artifacts / "execution"),
    "--recording-observations", str(config),
]
(root / "verification" / "cli-command.json").write_text(json.dumps(command, indent=2) + "\n")
result = subprocess.run(command, capture_output=True, text=True, check=False)
(root / "verification" / "cli-stdout.json").write_text(result.stdout)
(root / "verification" / "cli-stderr.log").write_text(result.stderr)
(root / "verification" / "cli-exit-code.txt").write_text(f"{result.returncode}\n")
raise SystemExit(result.returncode)
