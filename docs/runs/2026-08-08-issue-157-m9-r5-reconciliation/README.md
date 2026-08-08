# M9-R5 mechanical reconciliation (#157)

Status: terminal pre-runtime `Not Supported`.

This run record consumes the exact merged M9-R4 evidence without invoking the
formal consumer, Android, a model, a build, an oracle, or a review. It overlays
the committed auditor roles only in memory and invokes the frozen pure reducer
once. No R3/R4 file is changed.

## Decision

The exact R5 reducer output is `Not Supported`.

| Frozen gate | Result |
|---|---|
| six of six accountable | fail — 0/6 |
| six of six attempt evidence validated | fail — 0/6 |
| defect three of three supported | fail — 0/3 |
| control three of three locally rejected | fail — 0/3 |
| falsification six of six survived | fail — 0/6 |
| review identities unique and policy-bound | fail |
| contradiction rejected before side effect | pass |
| formal attempt inventory checksum-bound | pass |
| formal attempt artifacts exhaustively enumerated | fail |
| one formal attempt / zero retry / replacement | fail as a composite gate |

The numeric accounting remains one formal attempt, six ordered terminal rows,
six unique ExecutionRecord attempt identities, and zero retry, replacement, or
discretionary rerun. The two composite artifact/one-attempt gates fail because
the pre-runtime rows contain no attempt-evidence receipt that reverse-binds their
canonical ExecutionRecords. The root still contains exactly six exhaustive,
unique records and an exhaustive checksum ledger. This discrepancy is preserved,
not repaired, and is tracked for future packets by #158.

## Runtime interpretation

R4 stopped at `PORTFOLIO_FROZEN` with:

```text
M9RecoveryFormalError: target-specific Attack Plan was rejected: evidence expectations do not cover hypothesis requirements
```

The contradiction packet was rejected before side effects, then Context
Acquisition and the three-prior Hypothesis Portfolio completed. Mapping release,
fresh fixture creation, production admission, device work, model invocation,
runtime evidence, oracle, Finding, Project Risk Map, and Falsification Review did
not occur.

The raw reducer returns `formal_holdout_executed=true` because it reconciles one
formal attempt. That field does not mean a runtime lane began. The authoritative
R4 formal summary records `formal_holdout_executed=false`, zero source fixtures,
no default input method observed during formal work, and 0/6 accountable. The R5
decision is therefore pre-runtime qualification evidence, not an application
runtime FAIL or runtime discovery result.

## Immutable inputs

- R4 merge commit: `47a6e5b03a46a886ba35658dcaac9a5062bd973f`.
- R4 merge tree: `565c3bf3395a317f4b316527493788233760b0cc`.
- R4 evidence commit: `ac2756bcf7f4a86afa52239cdd359bcf82e83e92`.
- R3 ledger: 57 entries, SHA-256
  `0d3b311387dae768cf361a1f7683605a97600851ccb1e38c8ce2632b3ee9dc47`.
- R4 formal ledger: 27 entries, SHA-256
  `94488b89e52739e3d2fdd8d4d0633cc2feda104e90e5d2268ff51da598f28160`.
- Six R4 lane ledgers: 12/12 entries verified.
- R4 audit ledger: two entries, SHA-256
  `a5ea13cbc83ad23b9f8d6a1d207fe139cd7a73b76d314d502feb095c6403ba97`.
- Mapping raw SHA-256:
  `4da963ad23e5e8aca18e79328069a23a62a3071eb814d929246675fc7f4b84eb`.
- Mapping canonical SHA-256:
  `d69c0421ed68bf7de020326043fcf787250abbdb9aa0c9a10ecc3a2cc1eba8a4`.
- Contradiction audit canonical SHA-256:
  `ed594192326034c9a0eb576fbfa1fe76f29a0e5af5f1099074d2d187c9ab254e`.

## Exact reducer command

The following command was run exactly once. It wrote nothing and printed the
complete result now preserved as `reconciliation.json`:

```text
uv run python -c 'import json; from pathlib import Path; from aiverify.bench.m9_recovery_qualification import reconcile_formal_rows; repository=Path.cwd(); formal_root=repository/"docs/runs/2026-08-07-m9-r4-formal-attempt-01"; packet=json.loads((formal_root/"auditor-reconciliation-input.json").read_text(encoding="utf-8")); mapping=json.loads((repository/"bench/m9/recovery-v2/auditor/matched-pair.json").read_text(encoding="utf-8")); roles={item["lane_id"]: item["role"] for item in mapping["assignments"]}; rows=[]
for sealed in packet["rows"]:
 row=dict(sealed)
 if row.get("role") is not None: raise RuntimeError("sealed R4 role unexpectedly released")
 row["role"]=roles[row["lane_id"]]
 rows.append(row)
result=reconcile_formal_rows(rows, packet["contradiction"], auditor_mapping=mapping, expected_mapping_commitment_sha256="d69c0421ed68bf7de020326043fcf787250abbdb9aa0c9a10ecc3a2cc1eba8a4", expected_contradiction_audit_sha256="ed594192326034c9a0eb576fbfa1fe76f29a0e5af5f1099074d2d187c9ab254e", formal_attempt_inventory=packet["formal_attempt_inventory"], formal_attempt_inventory_receipt=packet["formal_attempt_inventory_receipt"], evidence_repository_root=repository); print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))'
```

Result: exit 0; aggregate `Not Supported`; complete raw output SHA-256
`a665db14da5c3cc18ff60016a602e0922f3f7e051de35332d99d7a3d7885437e`.

## Verification performed

Before reduction:

```text
git rev-parse HEAD
git rev-parse HEAD^{tree}
git rev-parse origin/main
git status --porcelain=v1 -uall | shasum -a 256
uv run python -c 'import json; from aiverify.bench.m9_recovery_formal import _verify_frozen_r3_ledger; print(json.dumps(_verify_frozen_r3_ledger(), sort_keys=True))'
(cd docs/runs/2026-08-07-m9-r4-formal-attempt-01 && shasum -a 256 -c checksums.sha256)
for lane in docs/runs/2026-08-07-m9-r4-formal-attempt-01/formal-artifacts/m9-r4-lane-*; do (cd "$lane" && shasum -a 256 -c checksums.sha256); done
(cd docs/runs/2026-08-08-issue-154-m9-r4-formal-execution-audit && shasum -a 256 -c checksums.sha256)
```

Results: exact clean merge/tree/origin seal; R3 57/57; R4 formal 27/27;
R4 lane 12/12; R4 audit 2/2. Mapping raw and canonical commitments matched.

The first focused run after R4 evidence was merged exposed a stale test fixture:

```text
/usr/bin/time -p uv run pytest tests/bench/test_m9_recovery_formal.py tests/bench/test_m9_recovery_qualification.py
```

Result: 91 passed, 1 failed because the test used the now-committed formal root
instead of an isolated temporary root. Only that test fixture was changed to
monkeypatch `FORMAL_ROOT` to a non-existent `tmp_path`. The consumer, reducer,
R3/R4 evidence, and formal result were not changed. The identical focused command
then passed 92/92 in 18.33 seconds; wall 18.51 seconds.

One preliminary full run passed 1010 tests and failed only the living-document
relative-link check because this README had not yet been created. The final full
run used:

```text
/usr/bin/time -p -o /private/tmp/m9-r5-full-final2.vvrA6C/time.txt uv run python -m pytest --junitxml=/private/tmp/m9-r5-full-final2.vvrA6C/junit.xml
```

Result: 1011 passed in 56.79 seconds; 0 failed, 0 errors, 0 skipped; wall 57.02
seconds. JUnit: 141,288 bytes, SHA-256
`1213af5f706157c038892d2b1e1f46b1d3cdfda12378ed8c75286ad9a12e579c`.
Timing receipt SHA-256:
`2aed30210c62c330ad24ec3c3d5316757e413cf12e6b128634934541acc063fe`.
These bulky transient outputs remain under `/private/tmp`; their exact path,
size, checksums, and result are committed in `verification.json`.

## Files and artifacts

- `reconciliation.json` — complete unmodified reducer return value.
- `interpretation.json` — explicit pre-runtime interpretation, gate split,
  role-overlay boundary, and source-of-truth precedence.
- `verification.json` — commands, test counts/timings, input/output identities,
  artifact inventory, tools, and protected-worktree invariant.
- `checksums.sha256` — ledger for this R5 record.
- Living source-of-truth updates: `CONTEXT.md`, `README.md`, `HANDOFF.md`, and the
  current capability claim matrix.
- Regression isolation: the static-preflight test now uses a temporary formal
  root after real evidence is committed.

There are no screenshots, layouts, logcat files, emulator steps, model receipts,
or manual UI steps in R5. Their absence is expected because reconciliation is a
pure evidence computation.

## Boundaries and follow-up

The original dirty worktree remained unchanged. R1/R2 were not reused in the R4
denominator. #136/#137 remain immutable and #137 remains Runtime Not Supported.
No runtime, production, upstream, physical-device, OEM, ColorOS, benchmark-rate,
recall, completeness, or automatic-repair claim is made.

#158 tracks future-only plan preclaim, terminal-row inventory binding, and honest
attempt-versus-runtime fields. It cannot authorize a second invocation of #154.
After this record merges, #154 and #157 can close and #128 can record the terminal
recovery outcome while linking #158 as independent open hardening.
