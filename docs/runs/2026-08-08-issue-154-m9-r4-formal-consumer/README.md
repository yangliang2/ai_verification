# M9-R4 Phase A formal consumer

Issue: [#154](https://github.com/yangliang2/ai_verification/issues/154)
Phase: A — merge the immutable consumer before formal start
Result: PASS
Recorded: 2026-08-08T06:30:48Z

This record seals the implementation and static verification of the recovery-v2
formal consumer. It is deliberately not a formal execution record. At the end of
Phase A, the formal attempt root and fresh source root were absent, device calls,
model calls, and formal lane attempts were all zero, and the frozen manifest still
reported `formal_holdout_executed=false`.

## Reviewed code seal

- Base / merged R3 hand-off:
  `6ec408f1aec57adfcd90e0e25e2453a9eda05fc1`
- Consumer code commit:
  `5c404d2bcf19b4edad7fb1f709e1124952b17fa6`
- Consumer tree:
  `5b1fa2ca2b952bdc49e293d92dcceabac337a7e2`
- Base-to-consumer diff SHA-256:
  `9a4fa807429fb0c43f755e6e5931e9a7a58bddebc7e48ba141e441d2783589a7`
- Worktree status SHA-256 at verification:
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

The base-to-consumer change contains 3,686 insertions and 37 deletions in seven
files. The evidence directory in this commit is documentation-only and does not
change the reviewed consumer seal.

## Frozen inputs

- R3 packet commitment:
  `a2ae1d8ca4902a500c67aa6107a0f42fe06a3948ca484305861d2d2670033225`
- Manifest SHA-256:
  `aa860f4b10144c2e6374912685ef914a420a234fc805d36cebb72b0c705629ad`
- R3 ledger SHA-256:
  `0d3b311387dae768cf361a1f7683605a97600851ccb1e38c8ce2632b3ee9dc47`
  with 57/57 entries verified
- Canonical mapping commitment:
  `d69c0421ed68bf7de020326043fcf787250abbdb9aa0c9a10ecc3a2cc1eba8a4`
- Raw mapping commitment:
  `4da963ad23e5e8aca18e79328069a23a62a3071eb814d929246675fc7f4b84eb`
- Defect source: commit `56b59e237b253bc52e2ce1141dce26af07503415`,
  tree `993432fb446913107df1bc0c040a05f8dae1c5b2`, APK 17,511,239
  bytes, SHA-256
  `41d7c3ff47f2f2d2a04942d11ab57c6c76ac7314ff6abf8dad14fd9b3149e55b`
- Control source: commit `038c8208307508ceedcb5dd07a4fe2794017644c`,
  tree `e658ec4cdbb25d8e75a04879e9e20a0c245832e9`, APK 17,511,449
  bytes, SHA-256
  `a1536cec09a33063f7796dc77e0effdf1847a3ad325dcef707216fa87d78386d`

Both source snapshots were clean and resolved to
`https://github.com/android/compose-samples.git`. The side-effect-free external
input check ran before any formal root claim.

## Implementation evidence

- `src/aiverify/bench/m9_recovery_formal.py` implements immutable preflight,
  contradiction rejection, monotonic mapping/admission/execution stages, the exact
  six-lane one-shot runner, terminal failure preservation, raw evidence
  normalization, clean-context review, and lane/root sealing.
- `src/aiverify/bench/m9_recovery_qualification.py` validates exact R3 identities,
  production/review identities, source/APK bytes, raw screenshot/layout/event/log
  lineage, typed absence, exhaustive lane and root ledgers, and the all-or-nothing
  R5 gate.
- `src/aiverify/runner/cli.py` and
  `src/aiverify/runner/execution_identity.py` expose the formal one-attempt and
  authoritative identity boundaries used by the consumer.
- `tests/bench/test_m9_recovery_formal.py`,
  `tests/bench/test_m9_recovery_qualification.py`, and
  `tests/runner/test_execution_identity.py` cover ordering, contradiction
  rejection, exact token and lifecycle evidence, terminal receipts, glob-aware
  absence, no retry/replacement, role leakage, mapping release, raw source
  reconstruction, root exhaustiveness, review isolation, and exact reduction.

Important fail-closed properties include:

- external source/APK prerequisites precede the irreversible formal-root claim;
- the contradiction packet is rejected without build, device, agent-runtime, or
  denominator effects;
- all six admissions finish before lane 01 starts, and each lane can enter exactly
  one terminal lifecycle in frozen order;
- generator, planner, executor, and reviewer inputs remain role-blind;
- normalized layout, screenshot, rotation, lifecycle, and checkpoint log evidence
  is independently recomputed from fixed runner sources;
- any missing artifact has a typed absence, including glob paths and internal raw
  source evidence, while a newly written checksum ledger is never falsely listed
  as absent;
- the root ledger is parsed and compared against the complete formal-root file set;
- R5 can return `Supported` only for contradiction pass, 6/6 accountable and
  evidence-valid lanes, defect 3/3 support, control 3/3 rejection, and 6/6 surviving
  independent reviews.

## Verification

### Focused tests

```text
/usr/bin/time -p uv run pytest \
  tests/bench/test_m9_recovery_formal.py \
  tests/bench/test_m9_recovery_qualification.py
```

Result: 92 passed in 16.18 seconds; wall clock 16.28 seconds.

### Full suite

```text
/usr/bin/time -p \
  -o /private/tmp/m9-r4-full-final-5c404d2.YpSjce/time.txt \
  uv run python -m pytest \
  --junitxml=/private/tmp/m9-r4-full-final-5c404d2.YpSjce/junit.xml
```

Result: 1,011 tests, 0 failures, 0 errors, 0 skipped. Pytest-reported
duration was 49.161 seconds; wall clock was 50.45 seconds. The JUnit report was
141,288 bytes with SHA-256
`7527ccc745fdd1921c8aa42c2fb9f57bb65536d7ce306a2b47699836e0ef0e9e`.
The timing receipt SHA-256 was
`a9e63f1e5f249029eaa7b7d55c4dcc2827e368f394a22f46024c0e7a565da09b`.

Before the authoritative JUnit run, preliminary console-only full-suite attempts
lost their terminal output capture; the first coincided with an unrelated host
process issuing `pkill -f "pytest -q"`. Those attempts are not acceptance evidence
and did not create either formal namespace. The JUnit run above is the terminal,
authoritative full-suite result.

### Frozen/static checks

```text
uv run python -m aiverify.bench.m9_recovery_formal --static-preflight
uv run python -m py_compile \
  src/aiverify/bench/m9_recovery_formal.py \
  src/aiverify/bench/m9_recovery_qualification.py
uv run python -m aiverify.bench.m9_recovery_qualification \
  --check-manifest bench/m9/m9-recovery-project-qualification-v2.json
git diff --check
```

All commands exited zero. Static preflight reported `status=passed`,
`side_effects=false`, `device_calls=0`, `model_calls=0`, and
`formal_lane_attempts=0`, with the exact manifest, packet, mapping, and 57-entry R3
ledger identities above. The manifest check and `py_compile` completed without
output. `git diff --check` found no whitespace errors.

The exact external source/APK validation command was:

```text
/usr/bin/time -p uv run python - <<'PY'
import json
from aiverify.bench.m9_recovery_formal import (
    FormalInputs,
    _source_bindings,
    _validate_formal_inputs,
)
inputs = FormalInputs(
    expected_consumer_commit="5c404d2bcf19b4edad7fb1f709e1124952b17fa6"
)
print(json.dumps(
    _validate_formal_inputs(inputs, _source_bindings(inputs)),
    sort_keys=True,
))
PY
```

It returned `status=passed`, `side_effects=false`,
`verified_before_formal_root_claim=true`, and `source_root_absent=true` in 0.28
seconds.

### Package build

```text
/usr/bin/time -p uv build \
  --out-dir /private/tmp/m9-r4-phase-a-package-5c404d2.NVPHj8
```

Result: wheel and source distribution built successfully in 3.36 seconds.

- Wheel: `aiverify-0.1.0-py3-none-any.whl`, SHA-256
  `866a269363084fb5c050c15b5e947509ed198cdf8ed2eb3f20ed75dd79ad99a7`
- Source distribution: `aiverify-0.1.0.tar.gz`, SHA-256
  `c280ff244e14498712a9010e2ff7777d203a25a22465bf68c1b5f2c04a0b85c3`
- Metadata: `aiverify` 0.1.0, Python >=3.11
- Wheel and sdist bytes for the four changed runtime modules matched the source
  tree exactly. Their SHA-256 values were:
  - formal consumer:
    `e8ea4b81c5f3d67ed70c0667c3baad1f7f9df8f063ce29a9cf12590e2575335a`
  - qualification validator:
    `c298337dfa428a1bbb1f88af72a083399e2bd43c59732d32bb375fe9ffdc5449`
  - runner CLI:
    `d0a47bcef3154b3d71c8be2c33ecd9e2139903034f37ab9efdca5904e6aaaf18`
  - execution identity:
    `9f27fcad0c739d182b4c4e08ca9eda68150bdfdbe0497a53a65c76d02a34cd29`

The package identities and byte equality were checked with `shasum -a 256` on
the output directory and source files, `unzip -p <wheel> <module> | shasum -a
256`, and `tar -xOf <sdist> aiverify-0.1.0/<module> | shasum -a 256` for each of
the four module paths listed above. Wheel metadata was read with `unzip -p`.

### Independent review

- [Standards review](standards-review.md): PASS, zero standards violations and
  zero judgement findings.
- [Spec review](spec-review.md): PASS, no remaining #154 finding.

Both reviews read the final commit/tree through Git objects. Neither reviewer
modified files or ran tests, a device, a model CLI, or the formal workflow.

## Tool identities

- Python 3.11.15
- Android CLI 1.0.15498356, SHA-256
  `288c28a83023fb2c2385dc9f7ed4497d3ef7d39111213bcdb4cb30a93d0243fc`
- adb 1.0.41 / 37.0.0-14910828, SHA-256
  `9fdf861259dc807937b13afdd5f053c7fda9f3b7726933fe0e0f45130ecb8dc7`
- codex-cli 0.144.6, SHA-256
  `80a3933d11a9d13ef806aa24f7bb8afc9169cfe4e9b09d6da6a92922cbde9cff`
- uv 0.11.7, SHA-256
  `40a78912c850286ea5756211f1f88c0928fb15b788869d46d4355cd4ac556023`
- git 2.50.1 (Apple Git-155), SHA-256
  `506cb2ddd061e2992c8ee7c53853340688b53d9fcec94c3aa936524cea5b40cb`

## Worktree isolation

The original dirty worktree `/Users/peter/projects/ai_verfication` remained
unchanged:

- branch `issue-73-accessibility-slice`
- HEAD `ef94cb543b76254687acab5e2de1b6527076d9ae`
- status SHA-256
  `af08d39f3854aa888b242408361083afe51117ad8ef078aa365cfaef19443ceb`
- tracked diff SHA-256
  `75e2cd7dc7750142ef17eab9e719f15cc2ee244600528ec6973a68e778239e57`
- staged diff SHA-256 was the empty digest
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

Those identities were collected without mutation using `git branch
--show-current`, `git rev-parse HEAD`, `git status --porcelain=v1
--untracked-files=all | shasum -a 256`, `git diff --binary | shasum -a 256`, and
`git diff --cached --binary | shasum -a 256` in the original worktree.

R1/R2 inputs were not read, copied, or reused. Issues #136 and #137 were not rerun,
copied, or modified; #137 remains Runtime Not Supported.

## Artifact inventory and known gaps

Committed Phase A artifacts:

- `README.md` — human-readable evidence and command results
- `verification.json` — machine-readable identities, counters, results, and
  external artifact inventory
- `standards-review.md` — independent Standards seal
- `spec-review.md` — independent Spec seal
- `checksums.sha256` — SHA-256 inventory for the four preceding files

External generated artifacts are not committed because package binaries and the
full per-test JUnit XML are reproducible build/test products rather than source or
formal-lane evidence. Their absolute paths, sizes where relevant, and SHA-256
digests are preserved here and in `verification.json`.

Phase B remains intentionally unperformed. No emulator/device query, APK install,
app launch, Codex production/review CLI invocation, screenshot/layout/logcat
capture, manual visual verification, mapping release, or formal lane attempt
occurred in Phase A. The next permitted action is to merge this exact consumer,
create a new clean worktree from the merge, revalidate every prerequisite, and run
the single approved `--execute` command once.
