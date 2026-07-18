# M4 aggregate (audited pilot conclusion)

This aggregate accepts exactly three admitted prospective real-change case packages: T426553, T426989, and replacement T409797. T337177 is retained as an excluded candidate outside the denominator.

| Task | Base | Candidate | APK SHA-256 | Journey/oracle | Accountability | Local conclusion |
|---|---|---|---|---|---|---|
| T426553 | `6ccb8d8` | `eeb74c8` | `2c281135…3819` | encoded external URI preserved | accountable | locally_supported |
| T426989 | `6ccb8d8` | `03fc1c4` | `f92d792d…6a7c` | non-article pages omit Read more | accountable | locally_supported |
| T409797 | `6ccb8d8` | `cd57c06` | `a67fb37b…9dfe` | Activity labels | non-accountable: no authenticated fixture | non_accountable |

Raw counts: planned 3, admitted 3, accountable 2, locally supported 2, locally rejected 0, non-accountable 1, excluded 1, replaced 1. These are observations only; this report does not calculate a detection rate, false-positive rate, Goldset result, or upstream acceptance rate. Prospective task injection is not source-level defect injection.

Verification command:

```sh
python3 -m json.tool docs/runs/2026-07-18-m4-aggregate/aggregate.json
sha256sum docs/runs/2026-07-18-m4-aggregate/aggregate.json
```

The structured and Markdown outputs are generated from the same committed case inventory. Case-level evidence: `../2026-07-18-m4-t426553/README.md`, `../2026-07-18-m4-t426989/README.md`, `../2026-07-18-m4-t409797/README.md`; exclusion evidence: `../2026-07-18-m4-t337177-exclusion/README.md`.

## M5 recommendation

Choose **additional real-change cases**. Require a stable fixture and an independently accountable Journey before pursuing historical-pair Goldset or controlled-mutation work; two cases are locally supported, but the replacement case is non-accountable and the pilot therefore lacks three accountable observations.
