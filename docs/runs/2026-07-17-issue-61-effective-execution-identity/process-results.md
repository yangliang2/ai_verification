# Verification commands and results

All commands ran from `/Users/peter/projects/ai_verfication` on 2026-07-17.

## Public API 35 emulator probe

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.runner \
  /Users/peter/projects/ai_verfication/docs/runs/2026-07-17-issue-61-effective-execution-identity/run-spec.yaml \
  --device emulator-5554 \
  --artifact-dir /Users/peter/projects/ai_verfication/docs/runs/2026-07-17-issue-61-effective-execution-identity/success-attempt/artifacts \
  --workdir /Users/peter/hosts/wikipedia \
  --model gpt-5.6-sol
```

```text
attempt c4c22d1d-d44f-42a6-ad1f-2a45ea16b796
ExecutionRecord schema 2
lifecycle completed; accounting eligible; process exit 0
total 36.015 seconds
L1 inconclusive; L2 inconclusive (no boundary event); L3 not applicable
```

The Android CLI deployment process returned 0. The exact local APK and the
device-installed base APK both hashed to
`a3060b8c00b7addec0aa17685df0ea96892b5097289e3b51a863b6234468c2bc`.

## Independent provenance reload

```bash
PYTHONPATH=src .venv/bin/python - <<'PY'
import json
from pathlib import Path
from aiverify.runner.execution_identity import verify_execution_provenance
from aiverify.runner.execution_record import load_execution_record

run = Path(
    "docs/runs/2026-07-17-issue-61-effective-execution-identity/success-attempt"
).resolve()
record = load_execution_record(run / "execution-record.json")
manifest = verify_execution_provenance(
    record["evidence_refs"]["execution_provenance"],
    attempt_id=record["attempt_id"],
    scenario=record["scenario"],
    base_dir=run,
)
role = manifest["roles"]["journey_driver"]["invocations"][0]
receipt = json.loads((run / role["path"]).read_text())
print(record["lifecycle_state"], record["process_outcome"]["exit_code"])
print(receipt["requested_model"], receipt["effective_model"])
print(manifest["apk"]["artifacts"][0]["sha256"])
print(manifest["deployment"]["installed_artifacts"][0]["sha256"])
PY
```

```text
completed 0
gpt-5.6-sol gpt-5.6-sol
a3060b8c00b7addec0aa17685df0ea96892b5097289e3b51a863b6234468c2bc
a3060b8c00b7addec0aa17685df0ea96892b5097289e3b51a863b6234468c2bc
audit passed; provenance a3963cea6f637a0cab6784e9b25c3da93144d388f8bd75bdf5a380383803b31a
```

## Recomputed-checksum mutation probe

The probe deep-copied the successful manifest, changed
`host.worktree.status`, wrote a new manifest, recomputed its outer SHA-256, and
called `verify_execution_provenance` with the new checksum.

```text
mutation: host.worktree.status
outer_checksum_recomputed: true
audit: rejected
reason: host status checksum mismatch
```

## Focused tests

```bash
.venv/bin/pytest -q \
  tests/runner/test_execution_identity.py \
  tests/runner/test_run_spec.py \
  tests/runner/test_codex_backend.py \
  tests/test_codex_cli_provider.py \
  tests/runner/test_cli.py \
  tests/runner/test_execution_record.py \
  tests/runner/test_journey.py \
  tests/bench/test_m3_reliability.py
```

```text
184 passed
```

## Complete suite and static checks

```bash
.venv/bin/pytest --collect-only -q | \
  awk -F': ' '/: [0-9]+$/{sum += $2} END{print sum}'
/usr/bin/time -p .venv/bin/pytest -q
git diff --check
.venv/bin/python -m compileall -q src tests
```

```text
511 tests collected
511 passed
real 14.93
user 5.54
sys 2.72
git diff --check: passed
compileall: passed
```

## Relevant versions

```text
macOS 26.3 build 25D125 arm64
Python 3.11.15
Android CLI 1.0.15498356
adb 1.0.41 / platform-tools 37.0.0-14910828
Codex CLI 0.144.5
git 2.50.1 (Apple Git-155)
```

