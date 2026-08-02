# Issue 80 — fresh attempt-complete M3 trust gate

This run is the preregistered fresh population for issue #80. The manifest was
committed before execution. It contains five seeds, baseline/defect roles, and
three repetitions per role: 30 lanes total. Historical populations are retained
as separate denominators.

## Result

- Final immutable-v3 audit: **PASSED**.
- First-attempt accountability: 30/30.
- Eventual accountability: 30/30.
- Baseline controls: 15/15 passed; zero accountable false positives.
- Expected defects: 15/15 caught at the expected oracle and defect class.
- Retries and operational interventions: 0.
- Execution time: 2855.805 seconds; L3 judge time: 164.718 seconds.
- API 35 emulator: `emulator-5554`, AVD `aiverify_api35`, Android 15.
- Application: `org.wikipedia.dev`, version code 50594, Wikipedia revision
  `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`.
- Codex CLI 0.144.6; effective journey and L3 models `gpt-5.6-sol`.

## Verification commands and results

```text
PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m pytest tests/bench/test_m3_reliability.py \
  --junitxml=docs/runs/2026-07-21-issue-80-m3-fresh/focused-junit.xml -q
# 87 passed, 0 failed, 0 errors, 0 skipped; JUnit time 3.364 s

PYTHONPATH=src /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m pytest \
  --junitxml=docs/runs/2026-07-21-issue-80-m3-fresh/full-junit.xml -q
# 674 passed, 0 failed, 0 errors, 0 skipped; JUnit time 17.039 s

PYTHONPATH=src WIKIPEDIA_SOURCE=/Users/peter/hosts/wikipedia \
  /Users/peter/projects/ai_verfication/.venv/bin/python \
  -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-issue80.yaml audit \
  --environment docs/runs/2026-07-21-issue-80-m3-fresh/audit-environment.json \
  --json-output docs/runs/2026-07-21-issue-80-m3-fresh/audit.json \
  --markdown-output docs/runs/2026-07-21-issue-80-m3-fresh/audit.md
# exit 0; M3 v3 overall PASSED

for pkg in anr oversized query swallowed search; do
  (cd docs/runs/2026-07-21-issue-80-m3-fresh/$pkg && \
    shasum -a 256 -c checksums.sha256)
done
# all 743 listed package entries OK
```

Each live lane was run serially through `python -m aiverify.runner` on the API 35
emulator after resetting night mode. The append-only ledger contains exactly 60
events: one `started` and one `finished` event for each of 30 invocations. There
are exactly 30 `attempt.json` and 30 `execution-record.json` files. No lane was
retried and no formal invocation was quarantined or discarded.

## Artifact inventory

- `attempt-ledger.jsonl`: append-only invocation ledger.
- `progress.json`: evidence-derived population summary.
- `audit.json` and `audit.md`: generated final audit model and report.
- `audit-environment.json`: audit host, tool, comparison, and package identity.
- `focused-junit.xml` and `full-junit.xml`: exact automated-test counts/timing.
- `execution-driver.log`: serial lane schedule, exit status, and timestamps.
- `builds/`: six Gradle build logs and APK SHA-256 records.
- `anr/`, `oversized/`, `query/`, `swallowed/`, `search/`: five package roots,
  each with six lanes, environment metadata, screenshots/layout/logs, runner and
  judge lineage, verdicts, and a package-level `checksums.sha256`.
- `checksums.sha256`: run-root inventory generated before independent review;
  the later independent report is intentionally outside its non-circular scope.

The APK binaries are too large for the repository and remain at
`/Users/peter/hosts/wikipedia/aiverify-builds/issue80/`. Their byte sizes and
SHA-256 identities are retained in each package environment and in `builds/`.
The baseline hash is
`7af65b50f282a2204595cb6e7a78a61a7c3370a06da2ee1306eb696982a1c957`;
the five defect hashes are recorded alongside their build logs.

## Deviations and known limits

Before live execution, one malformed shell build orchestration attempt failed to
apply its patch and created no candidate APK. Its temporary worktree and malformed
log filename were removed before the six clean isolated builds. It is outside the
formal lane population and did not invoke the runner.

The first final-audit invocation failed closed because package metadata named the
issue-80 source worktree while the recorded Python executable resides in the
original worktree virtual environment. The source code for execution was selected
with `PYTHONPATH=src` from the issue-80 worktree. Package `host.workspace` values
were corrected to the actual executable workspace, checksums regenerated, and the
evidence correction committed as `0dd30dd05ba09f382a72677da049c0fc8adb38a6`.
No lane output was edited or rerun.

The claim is limited to this Wikipedia host, Codex CLI backend, one API 35 emulator,
and the versioned five-seed slice. It is not a physical-device, ColorOS,
benchmark-wide, fully unattended Journey, or general multimodal reliability claim.
