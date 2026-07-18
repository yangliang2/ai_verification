# Issue #67 Portable Host Locator Verification

Date: 2026-07-18 (America/New_York)

Issue: `#67` under M3.1 trust-closure PRD `#58`

Implementation revision: `f340337ca703c1f3490e5698f4d8a38b0a6f0b37`

## Outcome

The runner now accepts a structured, portable Run Spec host locator:

```yaml
host_project:
  root: ${WIKIPEDIA_SOURCE}
  origin: https://github.com/wikimedia/apps-android-wikipedia
  commit: 6ccb8d85a21a8e34b96e4813d3caee5c690ece9b
```

The public loader resolves the same frozen Run Spec through either the declared
environment variable or `--host-project`. The runner defaults `--workdir` to the
resolved host. Effective Execution Identity retains the locator, resolution
source, resolved absolute path, expected origin/commit, and actual repository
identity.

Missing or relative roots, conflicting environment/CLI bindings, malformed
locators, and actual Git origin/commit contradictions fail closed before
deployment. Provenance verification reparses the checksummed Run Spec snapshot
with the retained resolved binding, so it does not depend on the verifier
machine's environment.

Legacy string-valued `host_project` inputs remain readable for historical
evidence. No #62 input, attempt, report, or checksum was modified.

## Exact verification commands and results

```bash
.venv/bin/pytest -o addopts='' \
  tests/runner/test_run_spec.py \
  tests/runner/test_execution_identity.py \
  tests/runner/test_cli.py
# 60 passed in 0.72s

.venv/bin/pytest -o addopts='' \
  tests/bench/test_m3_v3_audit.py \
  tests/bench/test_m3_rebaseline_audit.py \
  tests/bench/test_m3_reliability.py
# 97 passed in 8.04s

TIMEFMT='wall_seconds=%E'; time .venv/bin/pytest
# 525 passed in 15.44s; wall_seconds=15.58s

PYTHONPATH=src .venv/bin/python -m aiverify.runner --help | \
  rg -- '--host-project|--workdir'
# exit 0; both flags present; --workdir documents resolved-host default

.venv/bin/python -m compileall -q src
# exit 0

for d in docs/runs/2026-07-17-m3-v3-*-reliability \
  docs/runs/2026-07-17-m3-v3-final-audited-comparison; do
  PYTHONPATH=src .venv/bin/python \
    -m aiverify.bench.run_record_checksums "$d" --verify
done
# six historical v3 checksum inventories verified
```

## Implementation and test surfaces

- `HostProjectLocator` is the structured domain contract retained on `RunSpec`.
- The Run Spec loader resolves and validates environment/override bindings while
  preserving the checksummed source bytes.
- The public runner CLI exposes `--host-project` and derives its default
  execution workdir from the resolved host.
- Effective Execution Identity captures and verifies the portable declaration,
  resolved path, Git origin, and commit.
- Public-seam tests cover two-machine resolution, explicit override, missing and
  relative roots, conflicting bindings, CLI workdir behavior, identity capture,
  origin/commit rejection, tampering, and historical M3 replay.

## Versions and environment

- macOS 26.3 (arm64)
- Python 3.11.15
- pytest 9.0.3
- Git 2.50.1 (Apple Git-155)
- Repository: `yangliang2/ai_verification`
- Implementation revision: `f340337ca703c1f3490e5698f4d8a38b0a6f0b37`

## Device, build, and manual verification

No Android build, APK deployment, emulator interaction, physical-device check,
or upstream access was required or performed. This issue changes and verifies
the Run Spec/runner/Effective Execution Identity contract; it does not execute a
new M3.1 population. The existing committed v3 packages were checksum-verified
and replayed through their focused audit tests.

## Artifact inventory

- `README.md`: human-readable verification record.
- `verification.json`: structured result from the same recorded command facts.
- `checksums.sha256`: generated last; covers the other two files.

## Known gaps and claim boundaries

- This contract repair does not change the immutable #62 result (`6/30 FAILED`)
  and does not unblock M4.
- No fresh 30-lane population was preregistered or executed.
- Structured portable locators intentionally require an exact `${UPPER_CASE_VAR}`
  root and exact Git origin/commit; general path interpolation is unsupported.
- Legacy string paths remain supported only for compatibility and do not gain
  portable origin/commit binding automatically.
- No Wikimedia Phabricator comment, claim, GitHub pull request, or other upstream
  interaction occurred.
