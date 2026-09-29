# 2026-09-29 — Family-preparation fixture correction (cross-machine mapping predecessor)

Status: passed; the repaired gates are green, and the one remaining failure is
attributed and documented instead of mislabelled.

The runtime family-preparation gates pinned their predecessor at the committed
issue-206 `admit-family` staging root, whose terminal records another
workstation's absolute `candidate_root`; on any other machine every gate in
`tests/bench/test_runtime_family_preparation.py` (17) tripped
`mapping_predecessor_input_mismatch` before it could assert. This run points
the module at the locally reissued v2 stage from #225 and corrects the m7
failure attribution that the #209/#210/#211 run records had copied from each
other.

Boundary: no Gradle build, no Android CLI, no adb, no emulator or physical
device, no model, and no agent backend ran. The only network interaction is
the Gradle wrapper fetch that `test_m7_runtime_probe.py` itself performs; the
environment intercepts it at the TLS layer and this run neither repairs nor
bypasses that.

## Scope and identities

- Issue: none (correction of the DIL-M1 record set; consumer #211)
- Parent: [#199](https://github.com/yangliang2/ai_verification/issues/199)
- Branch: `main`
- Fixed point reviewed: `51dba6e` (`Record #211 post-observation fail-closed as the DIL-M1 chain head in HANDOFF`)
- Implementation commit: the commit carrying this run record
- Changed surface: `tests/bench/test_runtime_family_preparation.py`
- Corrected records: `docs/runs/2026-09-28-issue-209-runtime-attempt/`,
  `docs/runs/2026-09-29-issue-210-runtime-pre-observation-fail-closed/`,
  `docs/runs/2026-09-29-issue-211-post-observation-fail-closed/`

Delivered surface:

| Path | Lines | SHA-256 |
|---|---:|---|
| `tests/bench/test_runtime_family_preparation.py` | 768 | `b2a1522cceae5bdf36c6adfc32f1c0f0b2a053a17e751e30d6e9e0756dd4883b` |

## What was wrong

- `MAPPING_ROOT` pointed at
  `docs/runs/2026-08-29-issue-206-runtime-mapping-release/verification/family-stage-final`.
  Its `stage-terminal.json` records
  `candidate_root = /Users/peter/projects/ai_verfication/bench/runtime-calibration/opencalc-input-save-enabled-v1`
  (another workstation, including its historical directory-name typo), while
  `runtime_family_preparation._load_mapping_predecessor` requires
  `terminal["candidate_root"] == str(candidate.root)`. On this machine all 17
  gates in the module therefore raised `mapping_predecessor_input_mismatch`
  before reaching an assertion.
- The #209/#210/#211 run records attributed all 18 pre-existing failures to
  that fixture path — including the m7 failure, which never reads it.
  `test_m7_runtime_probe.py` builds `bench/fixtures/lifecycle-recovery-app`;
  the wrapper cannot fetch `gradle-9.1.0-bin.zip` because the TLS handshake to
  `services.gradle.org` is intercepted and the wrapper JVM rejects the
  interception certificate (`PKIX path building failed`), leaving a zero-byte
  `.zip.part` in the wrapper cache. That failure is network-bound, not
  path-bound.

## What changed

- `MAPPING_ROOT` now points at
  `docs/runs/2026-09-28-issue-225-runtime-mapping-reissue/verification/family-stage-final`
  (release `opencalc-runtime-mapping-release-v2`, identity `cd2c36ec…`), whose
  `candidate_root`/`source_root` are this machine's paths. The committed #206
  release stays on disk and stays verifiable: `tests/bench/test_runtime_mapping.py`
  still pins the v1 identity byte for byte, and `stage_acceptance.py` shows
  both stages remain structurally accepted — only v2 matches the local
  `candidate_root`.
- The misattribution is corrected in place in the three run records (README
  prose in all three, plus the `known_gaps` entry of #209's
  `verification/verification.json`), each pointing back at this record. The
  three corrected records' `checksums.sha256` are recomputed and
  re-verified.

## Acceptance evidence

| Command | Result | Artifact |
|---|---|---|
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python docs/runs/2026-09-29-family-preparation-fixture-correction/verification/stage_acceptance.py` | #206 stage `accepted` but its recorded `candidate_root` ≠ local; #225 v2 `accepted` and equal | `verification/stage-acceptance.txt` |
| `.venv/bin/python -m pytest tests/bench/test_runtime_family_preparation.py -q --junitxml=verification/focused-pytest.xml` | 17 passed in 5.1 s (the same 17 failed at `2a5d16b` and in the #211 recorded run) | `verification/focused-pytest.xml` |
| `.venv/bin/python -m pytest -q --junitxml=verification/full-pytest.xml` | 1536 tests, 1 failed (m7), 0 errors, 52 skipped, 2025.4 s | `verification/full-pytest.xml`, `verification/full-pytest-stdout.txt` |
| `diff` of the failure sets, #211 → this run | `2,18d1`: exactly the 17 `test_runtime_family_preparation` entries removed, nothing added | `verification/failures-diff-vs-issue-211.txt` |
| `uvx ruff check` and `uvx ruff format --check` on the changed test and on `stage_acceptance.py` | clean | — |
| `shasum -a 256 -c verification/checksums.sha256` (this record and the three corrected records) | every line OK | — |

Environment: macOS 26.1 (Darwin arm64), Python 3.12.13, pytest 9.1.1,
ruff 0.16.9, git 2.50.1 (Apple Git-155).

## Failure-set accounting

| Run | Tests | Failed | Skipped | Suite time |
|---|---:|---:|---:|---:|
| #211 baseline (`2a5d16b`) | 1494 | 18 | 52 | 635.4 s |
| #211 recorded (`1297257`) | 1536 | 18 | 52 | 646.7 s |
| This correction | 1536 | 1 | 52 | 2025.4 s |

The m7 failure is the only remaining one. The repaired gates account for only
+34.3 s of the wall-time growth (17 tests, 2.2 s → 36.5 s) and m7 for +1.4 s;
the rest is a machine-wide slowdown that also hits unrelated git-heavy tests
(e.g. `test_materialization_preserves_executable_and_symlink_source_entries`
2.3 s → 63.9 s), i.e. host load during this run, not a regression from this
change. `verification/duration-deltas-vs-issue-211.txt` lists the per-test
deltas.

## Known gaps

1. **m7 stays blocked in this environment.** The Gradle 9.1.0 distribution
   fetch fails at the TLS handshake (`PKIX path building failed`); no bypass
   was attempted and the pinned `distributionSha256Sum` in
   `gradle-wrapper.properties` stays meaningful. Remediation belongs to the
   environment (an approved distribution source or trust configuration), not
   to this repository.
2. **The #206 stage cannot serve as a local predecessor by design.** Its
   release identity embeds the issuing machine's absolute roots, so reuse on
   another machine requires reissuing the stage (as #225 did). The committed
   #206 release is deliberately kept as the frozen v1 contract fixture.
3. **Issue comments still carry the original attribution.** The #209, #210,
   and #211 evidence comments repeat the misattribution; each issue receives a
   short correction comment pointing here.

## How to re-verify

```text
shasum -a 256 -c verification/checksums.sha256
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python verification/stage_acceptance.py
.venv/bin/python -m pytest tests/bench/test_runtime_family_preparation.py -q
```

The three corrected records re-verify from their own directories:

```text
(cd ../2026-09-28-issue-209-runtime-attempt && shasum -a 256 -c checksums.sha256)
(cd ../2026-09-29-issue-210-runtime-pre-observation-fail-closed && shasum -a 256 -c verification/checksums.sha256)
(cd ../2026-09-29-issue-211-post-observation-fail-closed && shasum -a 256 -c verification/checksums.sha256)
```
