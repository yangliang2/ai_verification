# Prospective admission fixtures

These sources are copied into the exact frozen upstream checkout only for local
admission preflight. They are not upstream patches, formal M6 lanes, or evidence
that an upstream task is fixed.

Each fixture must establish a bounded, machine-checkable behavior oracle before
the task can be admitted. A fixture that passes on the frozen development base,
cannot reproduce the reported behavior, or depends on unbounded external state
is exclusion evidence rather than an admitted prospective case.
