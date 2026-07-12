# 2026-07-12 Run-record checksum inventory validation

Issue: #40

## Scope

This host-only validation introduces a deterministic checksum inventory for
durable run records. The inventory excludes `checksums.sha256` itself, avoiding
self-referential verification failure.

## Public Commands

```bash
PYTHONPATH=src python -m aiverify.bench.run_record_checksums \
  docs/runs/2026-07-12-run-record-checksum-inventory
PYTHONPATH=src python -m aiverify.bench.run_record_checksums --verify \
  docs/runs/2026-07-12-run-record-checksum-inventory
```

Expected result: generation writes `checksums.sha256`; verification exits `0`
only when every listed artifact remains present and unchanged.

## Verification

- Unit fixture: intact record verifies successfully; a changed covered artifact
  reports `checksum mismatch: <artifact>` and exits non-zero.
- No Android device, emulator, APK, screenshot, layout, or logcat artifact was
  used for this host-side checksum utility.

## Artifact Inventory

- `README.md` — validation record.
- `checksums.sha256` — generated inventory, deliberately excluded from itself.

## Known Gaps

- Existing historical checksum manifests are not rewritten by this issue.
- Artifact-producing issues remain responsible for deciding which durable
  artifacts to retain before generating their inventory.
