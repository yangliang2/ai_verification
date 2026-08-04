# M6 Qualification Case Package Aggregate

Cohort: `m6-qualification-v1`
Manifest SHA-256: `45e8ce551653542734b24ab5ae7f763383847fc9004360ff1ebabc10bbcff7b9`

The package is local-only and keeps historical and prospective tracks as separate populations.

## Track summaries

| Track | Cases | Attempts | Accountable attempts | Non-accountable attempts | Operational seconds |
|---|---:|---:|---:|---:|---:|
| historical | 3 | 18 | 18 | 0 | 84.49 |
| prospective | 3 | 18 | 18 | 0 | 325.84 |

## Lane accountability

Planned lanes: `36`; observed lanes: `36`; first-attempt accountable: `36`; eventual accountable: `36`; retries: `0`.

Historical and prospective lane populations are reconciled independently; their denominators are not merged.

## Historical exact observations

| State | Lanes | Raw tests | Raw failures | Outcomes |
|---|---:|---:|---:|---|
| pre_fix | 9 | 15 | 15 | `{"fail": 9}` |
| fixed | 9 | 15 | 0 | `{"pass": 9}` |

## Prospective local conclusions

| Slot | Conclusion | Adjudication agreement | Gaps |
|---|---|---|---:|
| P-01 | locally_supported | true | 0 |
| P-02 | locally_supported | true | 0 |
| P-03 | inconclusive | true | 1 |

## M7 route

Recommendation: **remediate fixture/execution/oracle/adjudication gaps** (`remediate_fixture_execution_oracle_adjudication_gaps`).
Reason: A frozen case or accountability gap remains in the local evidence.

## Operational record

Package duration seconds: `410.33`; backend time seconds: `None`; judge time seconds: `None`.

## Frozen slots

| Slot | Track | Package | Conclusion |
|---|---|---|---|
| H-01 | historical | `m6-h-01` | locally_supported |
| H-02 | historical | `m6-h-02` | locally_supported |
| H-03 | historical | `m6-h-03` | locally_supported |
| P-01 | prospective | `m6-p-01` | locally_supported |
| P-02 | prospective | `m6-p-02` | locally_supported |
| P-03 | prospective | `m6-p-03` | inconclusive |

## Scope boundary

Only the recorded local observations, accountability, adjudication, and operational timing are represented. No population-level or upstream conclusion is produced.
