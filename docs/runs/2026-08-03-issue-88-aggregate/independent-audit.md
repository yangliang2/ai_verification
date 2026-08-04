# Independent aggregate audit

Status: **PASS**

Auditor: `independent-verification-agent-m6-aggregate`.

| Check | Status | Actual | Expected |
|---|---|---|---|
| six_packages_loaded | pass | 6 | 6 |
| package_checksums_verified | pass | None | None |
| thirty_six_lanes | pass | 36 | 36 |
| eventual_accountability | pass | 36 | 36 |
| historical_pair_observations | pass | None | None |
| prospective_conclusions | pass | {'inconclusive': 1, 'locally_supported': 2} | {'inconclusive': 1, 'locally_supported': 2} |
| adjudications_agree | pass | None | None |
| provenance_complete | pass | None | None |
| single_route | pass | None | None |
| route_matches_frozen_gap | pass | None | None |
| route_is_local_only | pass | None | None |
| json_regenerates_byte_for_byte | pass | None | None |
| markdown_regenerates_byte_for_byte | pass | None | None |
| claim_boundary_is_clean | pass | None | None |
| package_hash_inventory | pass | None | None |
| attempt_ids_unique | pass | 36 | 36 |
| lane_ids_unique | pass | 36 | 36 |

The aggregate is local-only. The selected route is remediation because P-03 is adjudicated inconclusive against its frozen oracle contract.
