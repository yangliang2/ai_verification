# Verification commands and results

All commands ran from `/Users/peter/projects/ai_verfication` on 2026-07-17.

## Public API 35 emulator probe

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.runner \
  /Users/peter/projects/ai_verfication/docs/runs/2026-07-17-issue-61-effective-execution-identity/run-spec.yaml \
  --device emulator-5554 \
  --artifact-dir /Users/peter/projects/ai_verfication/docs/runs/2026-07-17-issue-61-effective-execution-identity/success-attempt-2/artifacts \
  --workdir /Users/peter/hosts/wikipedia \
  --model gpt-5.6-sol
```

```text
attempt 294732cf-1198-4a3d-9783-de7f94c208c0
ExecutionRecord schema 2
lifecycle completed; accounting eligible; process exit 0
total 72.597 seconds
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
    "docs/runs/2026-07-17-issue-61-effective-execution-identity/success-attempt-2"
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
print(record["evidence_refs"]["execution_provenance"]["sha256"])
PY
```

```text
completed 0
gpt-5.6-sol gpt-5.6-sol
a3060b8c00b7addec0aa17685df0ea96892b5097289e3b51a863b6234468c2bc
a3060b8c00b7addec0aa17685df0ea96892b5097289e3b51a863b6234468c2bc
87c4c7088549fdd9073ec85f7c96fbee01eb9662405973999733771055a2b79f
```

## Recomputed-checksum mutation probe

The committed executable probe deep-copies the final attempt, mutates four
independent provenance dimensions, recomputes every outer provenance checksum,
and calls the production verifier:

```bash
.venv/bin/python \
  docs/runs/2026-07-17-issue-61-effective-execution-identity/audit-mutations.py
```

```text
host.origin: rejected — host identity checksum mismatch
run_spec.package: rejected — Run Spec snapshot contradicts captured identity
deployment.process.args: rejected — deployment process checksum mismatch
journey_driver.session_cwd: rejected — role session cwd contradicts captured host
4 mutation checks passed
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
188 passed
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
515 tests collected
515 passed
real 13.59
user 5.70
sys 2.79
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
