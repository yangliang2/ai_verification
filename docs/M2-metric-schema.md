# M2 Metric Schema

This note defines the small metric context used for M2 seed summaries. It exists
because oracle verdict classes and benchmark taxonomy categories are related but
not the same thing.

## Field Separation

| Concept | Location | Meaning | Example |
|---|---|---|---|
| Seed detection outcome | top-level `verdict.json.metric_context.seed_outcome` | Benchmark result computed from oracle outcomes for the whole seed run. | `caught`, `missed`, `passed_control`, `false_positive` |
| Oracle outcome | `verdict.json.l1/l2/l3.outcome` | Per-oracle verdict result. | `fail`, `pass`, `inconclusive`, `not_run` |
| Oracle defect class | `verdict.json.l1/l2/l3.defect_class_hypothesis` and `metric_context.oracle_defect_classes` | Symptom class reported by the oracle. This is not the taxonomy root cause. | `state_loss`, `ui_rendering` |
| Taxonomy category | `scenario.metric_context.taxonomy_category` and top-level `metric_context.taxonomy_category` | Benchmark seed category or root-cause bucket used for reporting. | `config-change`, `navigation` |
| Taxonomy pattern | `scenario.metric_context.taxonomy_pattern_id` and top-level `metric_context.taxonomy_pattern_id` | Specific seed/pattern identifier. | `config-change-02`, `navigation-02` |

The current oracle verdict schema remains unchanged. In particular,
`defect_class_hypothesis` continues to describe the oracle symptom class. M2
aggregation must not treat it as the seed's taxonomy/root-cause category.

## Run Spec Metadata

Run specs may add optional metric metadata under `scenario.metric_context`:

```yaml
scenario:
  id: wikipedia-navigation-02-back-button-swallowed
  metric_context:
    seed_kind: injected_defect
    taxonomy_category: navigation
    taxonomy_pattern_id: navigation-02
    expected_oracle_level: L2
    expected_oracle_defect_class: state_loss
```

Supported values:

- `seed_kind`: `unspecified`, `injected_defect`, or `baseline_control`.
- `expected_oracle_level`: `L1`, `L2`, or `L3`.
- `expected_oracle_defect_class`: one of the current oracle classes:
  `crash_stability`, `state_loss`, `ui_rendering`, `performance_regression`, or
  `permission_security`.

`taxonomy_category` and `taxonomy_pattern_id` are intentionally free-form strings
for now. They record the benchmark seed vocabulary and may include M2-specific
seed families such as `ui-rendering` that are not yet first-class categories in
`src/aiverify/bench/taxonomy/taxonomy.yaml`.

## Top-Level Verdict Context

The runner writes parsed metadata plus computed oracle results into top-level
`verdict.json.metric_context`:

```json
{
  "seed_id": "wikipedia-navigation-02-back-button-swallowed",
  "seed_kind": "injected_defect",
  "seed_outcome": "caught",
  "taxonomy_category": "navigation",
  "taxonomy_pattern_id": "navigation-02",
  "expected_oracle_level": "L2",
  "expected_oracle_defect_class": "state_loss",
  "oracle_outcomes": {
    "L1": "inconclusive",
    "L2": "fail",
    "L3": "not_run"
  },
  "oracle_defect_classes": {
    "L1": null,
    "L2": "state_loss",
    "L3": null
  },
  "failed_oracles": ["L2"]
}
```

For `seed_kind: injected_defect`, the computed seed outcome is:

- `caught` when any oracle returns `fail`;
- `missed` when no oracle returns `fail`.

For `seed_kind: baseline_control`, the computed seed outcome is:

- `passed_control` when no oracle returns `fail`;
- `false_positive` when any oracle returns `fail`.

For `seed_kind: unspecified`, the runner uses the neutral outcomes `detected` or
`not_detected`.

## Current Cleanup Coverage

The following M2 run specs now carry metric context:

- `wikipedia-config-change-02-query-duplication`: taxonomy category
  `config-change`, pattern `config-change-02`, expected oracle `L2/state_loss`.
- `wikipedia-navigation-02-back-button-swallowed`: taxonomy category
  `navigation`, pattern `navigation-02`, expected oracle `L2/state_loss`.
- `wikipedia-ui-rendering-02-search-card-copy-mismatch`: taxonomy category
  `ui-rendering`, pattern `ui-rendering-02`, expected oracle `L3/ui_rendering`.

This cleanup is schema/documentation work only. It does not reinterpret historical
run records, and it does not change L1/L2/L3 oracle behavior.
