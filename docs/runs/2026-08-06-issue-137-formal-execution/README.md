# M9 #137 formal execution

Status: terminal `Not Supported` evidence. The exact #136 merged commit was
consumed once. The contradiction packet was rejected before side effects, all
six lanes were released in the approved order, and all six lanes reached a
terminal non-accountable record. No lane was retried or replaced.

## Frozen identity

- #136 merged commit: `7f24d3efe6f92b79de021b2641ba94e7e50ef5fd`.
- #135 implementation binding: `d3e03dc036a1fb8d0f7f314e7999b58294399242`.
- ProjectTarget origin: `https://github.com/android/architecture-samples.git`.
- Baseline commit/tree: `ee66e1526b84c026615df032c705842b7d2a521f` /
  `19455e693ec8c96c37a56aec55059a220826c5a3`.
- Defect commit/tree: `208575f78d59716669d0733b5ed3e08797b08787` /
  `34998af23aed59aa17eaf915d848ab1b916a63e2`.
- Source index SHA-256:
  `66fa95486f2c63e84dbb1ba1dd77a43ad34cdd6ecbd8c659e496e9a204e38585`.
- Application identity: package
  `com.example.android.architecture.blueprints.main`, activity
  `com.example.android.architecture.blueprints.todoapp.TodoActivity`, SDK
  min/target 21/35.
- Lane order: `m9-lane-01` through `m9-lane-06`.
- Frozen runner: `codex_cli`, `m9-production-seam-v1`,
  `emulator-5554` / `aiverify_api35` / API 35, requested driver/L3
  `codex-default`.
- Mapping commitment:
  `81aa8a18a3174bae566c006bb064803d8794a4add9f345f33e39022c2bf30a62`;
  raw mapping SHA-256:
  `2004d2c343dc63f19cb143b9332d24ae1f411b8433c44300294ec6e831ff987b`.
  Only commitment and verification metadata are persisted in
  `mapping-release.json`; clear assignments are not persisted in verifier
  inputs or this report.

The auditor used the hidden role only in memory for aggregate reconciliation.
After execution, role fields were removed from per-lane fixture/lane-result
receipts and root row listings before commit; the sanitization receipt is
`blinding-sanitization.json`. This changed no lane outcome, count, checksum
binding, or formal population state.

## Ordered gates and reconciliation

The executor performed these gates in order:

1. Exact #136 identity and contradiction packet audit.
2. Read-only Context Acquisition: `partial`, 64 facts, with unresolved
   coverage recorded.
3. Exactly three frozen hypotheses from the approved registry.
4. Target-specific Attack Plan generation and admission.
5. Six-packet neutral leakage audit.
6. Hidden mapping release and commitment verification.
7. Six one-attempt lanes in the frozen order.

The contradiction packet passed the pre-side-effect rejection audit and was
excluded from the denominator. The final reconciliation is:

| Gate | Result |
|---|---:|
| lanes reconciled | 6/6 |
| accountable | 0/6 |
| defect Finding support | 0/3 |
| control local rejection | 0/3 |
| independent Falsification Reviews | 6/6 complete/survived |
| retries | 0 |
| replacements | 0 |
| aggregate | `Not Supported` |

The six reviews survived their clean-context review contract, but they review
non-accountable/inconclusive lane records and therefore cannot turn them into
accountable runtime evidence or a Supported result.

## Formal command and result

Exact command:

```text
uv run --extra dev python -m aiverify.bench.m9_formal --artifact-root docs/runs/2026-08-06-issue-137-formal-execution --control-project /private/tmp/m9-136-candidate-a-control --defect-project /private/tmp/m9-136-option-a --fixture-root /private/tmp/m9-137-formal-fixtures-final
```

Result: six lane directories, six terminal `ExecutionRecord`s, 0/6
accountable, 0 Codex provider invocations, and 1.825 seconds total. Each lane
has its own 18-entry checksum inventory; the formal-time global inventory has
118 entries and was verified with `shasum -a 256 -c`.

The common failure was pre-runtime setup: the fresh emulator had no installed
copy of the package, and this exact command returned `returncode=1`, stdout
`Failed`, empty stderr:

```text
adb -s emulator-5554 shell pm clear com.example.android.architecture.blueprints.main
```

The six lanes consequently stopped before install, launch, Journey/driver,
L1/L2/L3, screenshot, layout, logcat, or runtime oracle capture. Each lane
still has a terminal non-accountable `ExecutionRecord`, `ResidualRisk`, raw
absence inventory, `Finding`/risk-map reduction, and independent Falsification
Review. This is valid adverse/non-accountable completion evidence; it is not a
runtime supported or rejected claim. The exact remediation for future runs is
in `src/aiverify/bench/m9_formal.py::_clear_package`: the Android `pm clear`
uninstalled-package response is treated as an already-clean state. The frozen
six-lane population was not rerun or replaced after that diagnosis.

## Verification commands

Targeted verification after the formal run and remediation:

```text
uv run --extra dev pytest -q tests/bench/test_m9_formal.py tests/runner/test_cli.py tests/agent/test_oracle_l3.py
→ 56 passed, 0 failed; command completed successfully.

git diff --check
→ exit 0.

uv run --extra dev python -m py_compile src/aiverify/bench/m9_formal.py src/aiverify/runner/cli.py src/aiverify/agent/oracle/l3.py
→ exit 0.
```

Full suite:

```text
/usr/bin/time -p uv run --extra dev pytest -q
→ 874 passed, 0 failed; real 30.11s, user 23.15s, sys 5.86s.
```

Package verification:

```text
uv build --quiet --out-dir docs/runs/2026-08-06-issue-137-formal-execution/package
→ package aiverify 0.1.0 built successfully.

sha256sum docs/runs/2026-08-06-issue-137-formal-execution/package/aiverify-0.1.0-py3-none-any.whl docs/runs/2026-08-06-issue-137-formal-execution/package/aiverify-0.1.0.tar.gz
→ wheel 392,057 bytes, SHA-256 `0a4646c482917d319169a18b203280a84d5a4a9709d96cf68681b9f6fb10f458`.
→ sdist 356,502 bytes, SHA-256 `21f6cc4ddbed7d932723d2afe17b816d63daa7a69982450a03ae69f9db8c20d5`.
```

Formal evidence checks:

```text
for each m9-lane-01..m9-lane-06:
  (cd formal-artifacts/<lane> && shasum -a 256 -c checksums.sha256)
→ 18/18 entries passed for each lane.

(cd docs/runs/2026-08-06-issue-137-formal-execution && shasum -a 256 -c checksums.sha256)
→ 118/118 formal-time entries passed.
```

The post-execution inventory, including this report, package artifacts, and
diagnosis receipts, is `post-execution-checksums.sha256`.

## Tool, device, and artifact inventory

Tool identity is recorded in `tool-versions.json`: CPython 3.11.15, uv
0.11.7, Codex CLI 0.144.6, Android CLI 1.0.15498356, adb 1.0.41 with platform
37.0.0-14910828, and OpenJDK 17.0.19. The connected device was
`emulator-5554`, API 35, model `sdk_gphone64_arm64`; it was not reached beyond
the package-clear setup command.

The frozen pair APK checksums, copied into each clean fixture preparation
receipt, are:

- defect APK: 24,681,461 bytes,
  `61063a0fd247eb03d1bd251b0d9359c3c2a5ea07cb8abe4b38d3daae57c153ac`;
- baseline APK: 24,681,606 bytes,
  `d38b30f17010da114b5585dadec8326eb76b04dfbae4a175f7cb2840a0093c66`.

Root artifacts include `contradiction-rejection.json`,
`context-acquisition.json`, `hypothesis-portfolio.json`,
`strategy-probes.json`, `attack-plan-generation.json`, `leakage-audit.json`,
`mapping-release.json`, `oracle-contract.json`,
`formal-execution-summary.json`, `final-reconciliation.json`,
`formal-execution-diagnosis.json`, `package-build.json`, `tool-versions.json`,
`blinding-sanitization.json`, and six `formal-artifacts/m9-lane-*` directories.
Each lane directory includes
the admission receipt, fixture preparation and APK binding, package-clear
receipt, ExecutionRecord, verdict, Effective Identity, raw-evidence inventory,
Finding/ResidualRisk/Project Risk Map, attempt evidence, independent review,
lane result, exception receipt, and checksum ledger.

No screenshot, layout dump, logcat, installed APK, effective driver identity,
effective L3 identity, Codex invocation receipt, or runtime oracle result was
produced. The absence is explicitly recorded rather than inferred as a pass or
failure of the application behavior.

## Manual steps, known gaps, and claim boundary

Manual steps performed: none. Device diagnostics were read-only:
`adb devices`, `adb -s emulator-5554 get-state`, API-35 property inspection,
and the frozen package-clear command. No production data, upstream project
state, device network policy, or original dirty worktree was changed.

Known gaps:

- The formal population is non-accountable at package-clear setup and has no
  runtime detection/rejection evidence.
- Effective driver/L3 identity is `null` because provider invocation was never
  reached; the requested identity remains `codex-default` in every admitted
  receipt.
- The #136 committed checksum ledger references three absent ignored artifact
  files (`artifacts/.gitignore` and the two package archives). Their expected
  hashes are preserved in the #136 ledger; an isolated rebuild did not produce
  those exact bytes. #137 records this historical gap and supplies a fresh
  durable package build/checksum instead of claiming recovery.

Local-only claim boundary: this run supports only the exact frozen public
snapshot, local APK/package artifacts, local API-35 emulator setup, ordered
admission/gate records, terminal six-lane accountability outcome, independent
review records, and committed evidence. It does not claim application runtime
behavior, detection rate, recall, completeness, project-wide coverage,
benchmark-scale capability, M8 results, production/upstream acceptance,
physical-device/OEM/ColorOS behavior, or automated repair.
