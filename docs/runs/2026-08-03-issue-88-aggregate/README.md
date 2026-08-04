# M6 aggregate — 2026-08-03

Status: **PASS (aggregate integrity); M7 route is remediation**

This run is the evidence-derived closeout for #88. It consumes exactly the six frozen Qualification Case Packages from `m6-qualification-v1`, verifies their referenced files and checksums, preserves historical and prospective populations separately, and emits one deterministic structured report plus one Markdown view.

## Inputs and identity

- Cohort manifest: `bench/m6/m6-qualification-v1.yaml`
- Manifest SHA-256: `45e8ce551653542734b24ab5ae7f763383847fc9004360ff1ebabc10bbcff7b9`
- Planned lanes: 36 (18 historical, 18 prospective)
- Packages: three historical (`H-01`–`H-03`) and three prospective (`P-01`–`P-03`)
- All source package checksums were verified before inclusion.

| Slot | Track | Package | SHA-256 |
|---|---|---|---|
| H-01 | historical | `docs/runs/2026-08-03-issue-86-historical-formal/packages/m6-h-01.json` | `3af5d84bdffd2210d41fa0ce2eca97517633a31273e08e830b12858b0ec224ea` |
| H-02 | historical | `docs/runs/2026-08-03-issue-86-historical-formal/packages/m6-h-02.json` | `dc05bd5b23c6d1c2558ecbe671596c7bf0a5ee794b91d41b79ac1e362c010e04` |
| H-03 | historical | `docs/runs/2026-08-03-issue-86-historical-formal/packages/m6-h-03.json` | `2fe06d8ccf892812f808d6c9f43d3c67bcbd0a3ac8a9bc53dbe5d7dcd3f38116` |
| P-01 | prospective | `docs/runs/2026-08-03-issue-87-prospective-formal/packages/m6-p-01.json` | `94b2f6a473019b5cc1a68a347f07304c50ed9cff69629a170b26925ec3d84fa4` |
| P-02 | prospective | `docs/runs/2026-08-03-issue-87-prospective-formal/packages/m6-p-02.json` | `900fd46023b802abed30a9e70de8f96145cdb1e200a1bfa60e331ada6eeae3f5` |
| P-03 | prospective | `docs/runs/2026-08-03-issue-87-prospective-formal/packages/m6-p-03.json` | `b96cc4c67e184c223a3ca5076eb03b08ba08218902179afebf8d9e32b621ba88` |

## Aggregate observations

- Lane inventory: 36 observed / 36 planned; 36 first attempts accountable; 36 eventual lanes accountable; 0 retries; 0 non-accountable attempts.
- Historical: 18 lanes, exact three repetitions for each of three matched pairs. The nine `pre_fix` observations all produced the preregistered `fail` oracle class (15 raw assertion failures over 15 tests); the nine `fixed` observations all produced `pass` (0 raw failures over 15 tests). Pair revisions and per-repetition outcomes are in `aggregate.json` under `historical.pairs`.
- Prospective: 18 lanes, nine `control` and nine `candidate`. P-01 and P-02 are locally supported (three candidate observations each). P-03 is `inconclusive` for all three candidate observations because the frozen fixture/oracle contract is internally contradictory; this is preserved as a gap and was not remediated or rerun.
- Adjudication: 6/6 package adjudications agree with their Verification Agent conclusions; no unexplained adjudication contradiction.
- Replacements and exclusions are copied as raw manifest records under `qualification.replacements` and `qualification.exclusions`; no post-invocation replacement was introduced.
- Interventions: three identical prospective “development candidate frozen before verification” records. Gaps: one P-03 frozen-oracle contradiction record.

## Operational values

- Package duration: 410.33 seconds.
- Build cost: 10 unique builds, 300.72 seconds (historical pre-fix/fixed builds, one shared prospective control build, and three prospective candidate builds).
- Attempt execution time: 54.41 seconds from preserved ExecutionRecords.
- Backend and judge time: not recorded by the six committed package contracts; the report emits `null` plus explicit `unrecorded_fields` rather than inventing values.
- Build log, APK/deployment receipts, attempt ledgers, provenance, verdicts, and other referenced artifacts remain checksum-bound by their package envelopes.

## Recommendation

Exactly one M7 route is selected:

`remediate_fixture_execution_oracle_adjudication_gaps`

The route is caused by the preserved P-03 contradiction and its `inconclusive` local conclusion. The M7 scale gate is false only because the aggregate has a recorded gap; all 36 lanes are otherwise accountable, historical fixed observations pass, historical pre-fix observations fail as expected, provenance is complete, and adjudication agrees. No M7 implementation or upstream interaction is started by this run.

## Commands and results

The exact aggregate invocation and byte-for-byte regeneration commands are in [`aggregate-command.txt`](aggregate-command.txt). The committed runner is [`run-aggregate.sh`](run-aggregate.sh).

- Aggregate generation: exit `0`; [`aggregate.json`](aggregate.json) SHA-256 `e6bce157336ffd95e017dcd7deffd1424f5ce3abdba9a92ec868415b8a7243a4`; [`aggregate.md`](aggregate.md) SHA-256 `9b2ff91d23f5f8df9e5589b5117f12163a1033a3608bf6c1158192edacbcec5d`.
- Regeneration: exit `0`; `cmp -s` for JSON and Markdown both returned `0`; regenerated copies are under [`regen/`](regen/).
- Independent audit: exit `0`, status PASS; command and hashes are in [`independent-audit-command.txt`](independent-audit-command.txt), with the machine report [`independent-audit.json`](independent-audit.json) and human report [`independent-audit.md`](independent-audit.md).
- Targeted package/aggregate tests: 19 collected, 19 passed in 4.78 seconds; log [`package-tests.log`](package-tests.log), timing [`package-tests.time`](package-tests.time).
- Full suite: 715 collected, 715 passed in 19.67 seconds; log [`full-suite.log`](full-suite.log), timing [`full-suite.time`](full-suite.time). Three pre-existing `DeprecationWarning`s from `src/aiverify/agent/oracle/l2.py:123` remain.
- Wheel/source build: `uv build` exit `0`; log [`build.log`](build.log).

Artifact inventory: [`aggregate.json`](aggregate.json), [`aggregate.md`](aggregate.md), [`regen/`](regen/), [`independent-audit.json`](independent-audit.json), [`independent-audit.md`](independent-audit.md), [`independent_audit.py`](independent_audit.py), [`run-aggregate.sh`](run-aggregate.sh), command records, full/targeted test logs and timings, collection logs, and build log. SHA-256 values for every committed run artifact are in [`artifact-checksums.txt`](artifact-checksums.txt).

Tool versions used: `uv 0.11.7`, `git 2.50.1`, Python `3.14.4`, `pytest 9.1.1`, `jsonschema 4.26.0`, and `PyYAML 6.0.3`.

## Independent conclusion and limitations

`independent-verification-agent-m6-aggregate` independently reloaded all six packages with reference verification enabled, re-derived the aggregate, checked package/lane/attempt identity uniqueness, compared both renderings byte-for-byte, checked the local-only claim boundary, and verified the single remediation route. The audit is PASS.

This is local qualification evidence only. It does not claim population-level capability, physical/OEM coverage, or any external repository acceptance. Backend/judge timing is a known instrumentation gap. P-03 remains frozen and inconclusive as required by the out-of-scope rule; follow-up should repair the fixture/oracle contract in a separate issue before any replacement or rerun is considered.
