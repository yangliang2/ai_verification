# Discovery Campaign orchestrates discovery above Run Spec

## Context

M7 must find quality risk in both a single change and a complete project. The
current `Run Spec` is intentionally a single reproducible execution contract:
it binds a host checkout, build/deployment metadata, one scenario, and oracle
assertions. A project-wide risk search needs a different lifecycle: preserve
provenance-bound context, make uncertainty explicit, derive causal hypotheses,
select bounded attacks, and keep unresolved risk visible before an experiment
exists.

## Decision

Introduce `Discovery Campaign` as the domain contract above `Run Spec`.

The campaign owns `ChangeTarget` or `ProjectTarget`, a versioned `Quality Context
Graph`, `Quality Contract` and `Contract Drift` records, `Risk Hypothesis` and
`Failure Chain` reasoning, `Attack Plan` admission, and the resulting `Finding`,
`Residual Risk`, and `Project Risk Map`. An admitted plan may generate one or
more Run Specs; each Run Spec remains responsible for exactly one reproducible
execution and its existing execution identity/oracle contracts remain unchanged.

Admission is a side-effect-free, fail-closed boundary. Missing fixtures,
evidence expectations, oracle, claim boundary, supporting facts, or a frozen
hypothesis reject the plan before device, build, or external project actions.
Contradictory or stale supporting facts are never promoted to evidence.

## Rationale

Keeping discovery above Run Spec lets a complete project be explored without
inventing a fake diff or overloading an execution manifest with causal reasoning.
It also preserves the M6 accountability seam: a suspicion can be recorded and
ranked without being counted as a Finding, while a concrete experiment still
enters the existing Run Spec and ExecutionRecord path.

The campaign's derivation boundary is strategy-selected and versioned. A
strategy declares the compatible Risk Prior and Attack Operator identities and
target modes, then receives only the target, immutable Quality Context Graph,
and mode-specific Change inputs. Selection and result identity are checked
before a campaign can reach Attack Plan admission. The M7 temporal strategy
remains the compatibility default; future families must opt in explicitly and
cannot replace or reinterpret an earlier family.

## Rejected alternatives

- **Expand Run Spec into a scanner:** conflates search and execution, makes
  project targets ambiguous, and weakens reproducibility/accountability.
- **Use free-form prompt output:** loses provenance, uncertainty, and strict
  admission checks, so unsupported inference can become an apparent verdict.
- **Create an organization-wide knowledge graph:** exceeds M7 scope and adds
  mutable state before the first vertical discovery slice is proven.
