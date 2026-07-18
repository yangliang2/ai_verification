# M3 V3 Immutable Preregistration

Frozen at `2026-07-18T03:20:36Z` before any v3 lane execution for issue `#62`.

## Fixed population and policy

- Manifest: `bench/goldset/m3-reliability-slice-v3.yaml`
- Source revision: `77cf4ae61e6768cb2030474613e42391407d295c`
- Five unchanged Run Specs; baseline/defect × three repetitions = 30 fresh lanes.
- At most two attempts per lane; accountable attempts cannot be retried.
- Required result: 30/30 eventual accountability, 15/15 passing controls with
  zero false positives, and 15/15 defects caught at the expected oracle/class.
- Failed or exhausted lanes remain in the immutable v3 package; no lane replacement
  and no original/v2/v3 denominator merge is permitted.

`plan.json` is the pre-execution public-runner plan. It contains exactly 30 unique
pending lane identities and no attempt evidence.

## Fixed execution identity

- Wikipedia: `/Users/peter/hosts/wikipedia` at
  `6ccb8d85a21a8e34b96e4813d3caee5c690ece9b`, clean worktree.
- Application: `org.wikipedia.dev`, versionCode `50594`.
- Device: `emulator-5554`, AVD `aiverify_api35`, Android 15/API 35,
  fingerprint `google/sdk_gphone64_arm64/emu64a:15/AE3A.240806.043/12960925:userdebug/dev-keys`.
- Backend: Codex CLI `0.144.5`; Journey driver and L3 judge model
  `gpt-5.6-sol` with no command override.
- Android CLI `1.0.15498356`; adb `1.0.41` / platform-tools
  `37.0.0-14910828`; Python `3.11.15`; pytest `9.0.3`; OpenJDK `17.0.19`;
  Gradle `9.5.1`; git `2.50.1 (Apple Git-155)`; macOS `26.3 (25D125)` arm64.

Every formal attempt must go through `python -m aiverify.runner`, pass the live
validation gate, retain a schema-v2 `ExecutionRecord`, and verify its checksummed
`execution-provenance.json` before contributing an oracle outcome.

## Immutable historical anchors

- Original manifest SHA-256:
  `8017320a27a5a8e0a01fff1357abf09edf0164abf59e764dc843b5335c0271b3`
- Original final checksum-manifest SHA-256:
  `a07238f51b65e5dc6e65ee69dfa6f4876609227e99e85f846a1371212d593e1f`
- V2 manifest SHA-256:
  `c4c0cb8f331ae3e09db8663f8041335ef4614181337551962d5b9a662de8e6cb`
- V2 final checksum-manifest SHA-256:
  `246e798d991d322e277fcdce54455e42f62a00f2a520eb33cf52cbf7968f8911`

The final audit must re-derive and verify both historical reports and all ten
historical evidence-package checksum anchors without editing their bytes.

## Pre-execution verification

```bash
PYTHONPATH=src .venv/bin/python -m aiverify.bench.m3_reliability \
  --manifest bench/goldset/m3-reliability-slice-v3.yaml \
  plan --json-output docs/runs/2026-07-17-m3-v3-preregistration/plan.json
.venv/bin/pytest
```

Results: 30/30 lanes `pending`; `518 passed in 13.23s`.
