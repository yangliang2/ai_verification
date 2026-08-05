"""Fail-closed admission and local oracle for the M7-R1 runtime probe.

The runtime probe is intentionally a small envelope around the existing Android
Run Spec and runner contracts.  It freezes the source, change input, build
recipe, target profile, and six-lane policy before a device side effect is
allowed.  This module does not run Journeys; callers pass an admitted lane to
``aiverify.runner`` and persist its returned ExecutionRecord/identity artifacts.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from aiverify.runner.command import (
    CommandResult,
    CommandRunner,
    SubprocessCommandRunner,
)

_SCHEMA_PATH = Path(__file__).with_name("m7_runtime_probe_schema.json")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TEMPORAL_RESULT = re.compile(
    r"TEMPORAL_RESULT\s+delay_ms=(?P<delay>\d+)\s+"
    r"latency_ms=(?P<latency>\d+)\s+thread=(?P<thread>[A-Za-z0-9._-]+)\s+"
    r"summary=(?P<summary>[^\s]+)"
)


class RuntimeProbeError(ValueError):
    """Raised when a frozen runtime-probe input is invalid."""

    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(dict.fromkeys(str(error) for error in errors))
        super().__init__("runtime probe is invalid:\n" + "\n".join(f"- {e}" for e in self.errors))


@dataclass(frozen=True)
class RuntimeProbeManifest:
    """Frozen manifest plus the exact bytes consumed to load it."""

    source_path: Path
    source_sha256: str
    canonical_sha256: str
    document: Mapping[str, Any]

    @property
    def probe_id(self) -> str:
        return str(self.document["probe_id"])

    @property
    def cells(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.document["cells"])


@dataclass(frozen=True)
class TemporalOracleResult:
    """Local, bounded observation of one synchronous weather call."""

    conclusion: str
    observation: Mapping[str, Any]
    rationale: str
    evidence_ref: str = "logcat:TemporalProbe/TEMPORAL_RESULT"

    def to_dict(self) -> dict[str, Any]:
        return {
            "oracle": "m7-r1-temporal-main-thread-v1",
            "conclusion": self.conclusion,
            "observation": dict(self.observation),
            "rationale": self.rationale,
            "evidence_ref": self.evidence_ref,
            "claim_boundary": "local fixture and bounded runtime observation only",
        }


@dataclass(frozen=True)
class RuntimeProbeAdmission:
    """Deterministic preflight receipt; ``side_effects`` means device effects."""

    manifest: RuntimeProbeManifest
    admitted: bool
    reason_codes: tuple[str, ...]
    checks: tuple[Mapping[str, Any], ...]
    lanes: tuple[Mapping[str, Any], ...]
    build_receipts: tuple[Mapping[str, Any], ...]
    apk_snapshots: tuple[Mapping[str, Any], ...]
    side_effects: bool
    formal_denominator: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "probe_id": self.manifest.probe_id,
            "manifest_sha256": self.manifest.source_sha256,
            "canonical_manifest_sha256": self.manifest.canonical_sha256,
            "admitted": self.admitted,
            "reason_codes": list(self.reason_codes),
            "checks": [dict(check) for check in self.checks],
            "lanes": [dict(lane) for lane in self.lanes],
            "build_receipts": [dict(receipt) for receipt in self.build_receipts],
            "apk_snapshots": [dict(snapshot) for snapshot in self.apk_snapshots],
            "side_effects": self.side_effects,
            "formal_denominator": self.formal_denominator,
            "claim_boundary": dict(self.manifest.document["claim_boundary"]),
        }


def load_runtime_manifest(path: str | Path) -> RuntimeProbeManifest:
    """Load a frozen manifest and fail closed on schema or identity errors."""

    source_path = Path(path).resolve()
    try:
        raw = source_path.read_bytes()
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RuntimeProbeError) as error:
        raise RuntimeProbeError((f"manifest cannot be read: {error}",)) from error
    if not isinstance(document, dict):
        raise RuntimeProbeError(("manifest root must be an object",))
    try:
        schema = load_schema()
        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(schema).iter_errors(document),
            key=lambda error: (tuple(str(item) for item in error.absolute_path), error.message),
        )
    except Exception as error:
        raise RuntimeProbeError((f"manifest schema is invalid: {error}",)) from error
    if errors:
        raise RuntimeProbeError(tuple(_render_schema_error(error) for error in errors))
    semantic_errors = _manifest_errors(document)
    if semantic_errors:
        raise RuntimeProbeError(semantic_errors)
    canonical = _canonical_bytes(document)
    return RuntimeProbeManifest(
        source_path=source_path,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        canonical_sha256=hashlib.sha256(canonical).hexdigest(),
        document=document,
    )


def load_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def self_validate_schema() -> None:
    Draft202012Validator.check_schema(load_schema())


def admit_runtime_probe(
    manifest_path: str | Path,
    *,
    repo_root: str | Path | None = None,
    run_build: bool = False,
    check_device: bool = False,
    artifact_root: str | Path | None = None,
    command_runner: CommandRunner | None = None,
) -> RuntimeProbeAdmission:
    """Run source/build/target admission without installing or launching an APK.

    ``run_build`` is an explicit host-side action.  Device inspection is opt-in
    and read-only; this function never installs, launches, or changes network
    state.  Formal lanes therefore cannot accidentally start from a partial
    receipt.
    """

    manifest = load_runtime_manifest(manifest_path)
    root = Path(repo_root).resolve() if repo_root is not None else manifest.source_path.parents[3]
    runner = command_runner or SubprocessCommandRunner()
    checks: list[Mapping[str, Any]] = []
    reasons: list[str] = []
    build_receipts: list[Mapping[str, Any]] = []
    apk_snapshots: list[Mapping[str, Any]] = []
    lanes: list[Mapping[str, Any]] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "status": "pass" if passed else "fail", "detail": detail})

    source = manifest.document["source_identity"]
    for artifact in (*source["source_files"], source["context_manifest"], source["change_input"]):
        path = root / str(artifact["path"])
        expected = str(artifact["sha256"])
        actual = _sha256_file(path) if path.is_file() else None
        passed = actual == expected
        check(f"sha256:{artifact['path']}", passed, f"expected={expected} actual={actual}")
        if not passed:
            reasons.append("source_checksum_mismatch")

    build = manifest.document["build"]
    host_project = root / str(build["host_project"])
    wrapper = host_project / str(build["gradle_wrapper"])
    host_present = host_project.is_dir() and wrapper.is_file()
    check("host_project", host_present, str(host_project))
    if not host_present:
        reasons.append("host_project_missing")

    tool_versions = manifest.document["tool_policy"]
    for tool_name, command in (
        ("android_cli", [str(tool_versions["android_cli"]["binary"]), "--version"]),
        ("adb", [str(tool_versions["adb"]["binary"]), "version"]),
    ):
        result = runner.run(command, cwd=root, timeout_seconds=30)
        passed = result.returncode == 0 and bool(result.stdout.strip() or result.stderr.strip())
        check(tool_name, passed, _command_detail(result))
        if not passed:
            reasons.append(f"{tool_name}_unavailable")

    if check_device:
        device_reasons = _check_device(manifest.document["target"], runner)
        checks.extend(device_reasons[0])
        reasons.extend(device_reasons[1])

    variants = {str(item["cell_id"]): item for item in build["variants"]}
    run_specs = {str(item["cell_id"]): item for item in manifest.document["run_specs"]}
    if run_build and host_present:
        for cell in manifest.cells:
            cell_id = str(cell["cell_id"])
            variant = variants[cell_id]
            command = [str(build["gradle_wrapper"]), *map(str, build["base_args"])]
            for key, value in variant["gradle_properties"].items():
                command.append(f"-P{key}={value}")
            snapshot = (
                Path(artifact_root).resolve() / "build" / f"{cell_id}.apk"
                if artifact_root is not None
                else None
            )
            if snapshot is not None and snapshot.is_file():
                # Reuse the immutable APK captured by the first admission. A
                # later Gradle invocation can change signing/zip metadata even
                # when source inputs are identical; rebuilding here would make
                # the lane identity contradictory. Source checksums and APK
                # metadata are still revalidated below.
                apk = snapshot
                apk_hash = _sha256_file(apk)
                receipt = {
                    "cell_id": cell_id,
                    "command": command,
                    "reused_snapshot": True,
                    "returncode": 0,
                    "seconds": 0.0,
                    "apk": str(apk),
                    "apk_sha256": apk_hash,
                    "stdout_tail": "",
                    "stderr_tail": "",
                }
                snapshot_receipt = {
                    "cell_id": cell_id,
                    "path": str(snapshot),
                    "sha256": apk_hash,
                }
                apk_snapshots.append(snapshot_receipt)
                receipt["snapshot"] = snapshot_receipt
                result_returncode = 0
                result_detail = "reused immutable admission snapshot"
            else:
                started = time.monotonic()
                result = runner.run(command, cwd=host_project, timeout_seconds=build["timeout_seconds"])
                seconds = round(time.monotonic() - started, 3)
                apk = host_project / str(build["apk_relpath"])
                apk_hash = _sha256_file(apk) if apk.is_file() else None
                receipt = {
                    "cell_id": cell_id,
                    "command": command,
                    "reused_snapshot": False,
                    "returncode": result.returncode,
                    "seconds": seconds,
                    "apk": str(apk),
                    "apk_sha256": apk_hash,
                    "stdout_tail": result.stdout[-2000:],
                    "stderr_tail": result.stderr[-2000:],
                }
                result_returncode = result.returncode
                result_detail = _command_detail(result)
                if result.returncode == 0 and apk_hash is not None and snapshot is not None:
                    snapshot.parent.mkdir(parents=True, exist_ok=True)
                    if snapshot.exists():
                        reasons.append(f"evidence_exists_with_different_hash:{snapshot}")
                    else:
                        shutil.copy2(apk, snapshot)
                        snapshot_receipt = {
                            "cell_id": cell_id,
                            "path": str(snapshot),
                            "sha256": _sha256_file(snapshot),
                        }
                        apk_snapshots.append(snapshot_receipt)
                        receipt["snapshot"] = snapshot_receipt
            build_receipts.append(receipt)
            built = result_returncode == 0 and apk_hash is not None
            check(f"build:{cell_id}", built, result_detail)
            if not built:
                reasons.append(f"build_failed:{cell_id}")
                continue
            metadata_ok, metadata_detail = _apk_metadata(
                apk,
                package=str(variant["package"]),
                activity=str(variant["activity"]),
            )
            check(f"apk_metadata:{cell_id}", metadata_ok, metadata_detail)
            if not metadata_ok:
                reasons.append(f"apk_metadata_mismatch:{cell_id}")
            network_ok, network_detail = _apk_network_policy(apk)
            check(f"network_policy:{cell_id}", network_ok, network_detail)
            if not network_ok:
                reasons.append(f"network_policy_not_proven:{cell_id}")
            spec_path = root / str(run_specs[cell_id]["path"])
            spec_hash = _sha256_file(spec_path) if spec_path.is_file() else None
            spec_ok = spec_hash == str(run_specs[cell_id]["sha256"])
            check(f"run_spec:{cell_id}", spec_ok, f"expected={run_specs[cell_id]['sha256']} actual={spec_hash}")
            if not spec_ok:
                reasons.append(f"run_spec_checksum_mismatch:{cell_id}")
            for repetition in range(1, int(cell["repetitions"]) + 1):
                lanes.append(
                    {
                        "lane_id": f"{cell_id}-r{repetition}",
                        "cell_id": cell_id,
                        "repetition": repetition,
                        "attempts": 1,
                        "retry_after_accountable": False,
                        "run_spec": str(run_specs[cell_id]["path"]),
                        "run_spec_sha256": spec_hash,
                        "apk": {"path": str(build["apk_relpath"]), "sha256": apk_hash},
                        "package": variant["package"],
                        "activity": variant["activity"],
                    }
                )
    else:
        reasons.append("build_not_run")
        for cell in manifest.cells:
            check(f"build:{cell['cell_id']}", False, "explicit run_build=False")

    expected_lanes = int(manifest.document["policy"]["planned_lanes"])
    complete = (
        not reasons
        and len(lanes) == expected_lanes
        and len(build_receipts) == len(manifest.cells)
    )
    # The receipt itself has no device side effect.  A later runner invocation
    # must explicitly consume this admitted result before install/launch.
    return RuntimeProbeAdmission(
        manifest=manifest,
        admitted=complete,
        reason_codes=tuple(dict.fromkeys(reasons)),
        checks=tuple(checks),
        lanes=tuple(lanes if complete else ()),
        build_receipts=tuple(build_receipts),
        apk_snapshots=tuple(apk_snapshots),
        side_effects=False,
        formal_denominator=complete,
    )


def evaluate_temporal_oracle(logcat: str, *, threshold_ms: int = 200) -> TemporalOracleResult:
    """Evaluate only the preregistered main-thread temporal contract."""

    matches = list(_TEMPORAL_RESULT.finditer(logcat))
    if not matches:
        return TemporalOracleResult(
            conclusion="inconclusive",
            observation={"events": 0},
            rationale="No TemporalProbe result was captured; no runtime claim is made.",
        )
    match = matches[-1]
    delay_ms = int(match.group("delay"))
    latency_ms = int(match.group("latency"))
    thread = match.group("thread")
    summary = match.group("summary")
    observation = {
        "events": len(matches),
        "delay_ms": delay_ms,
        "latency_ms": latency_ms,
        "caller_thread": thread,
        "summary": summary,
        "threshold_ms": threshold_ms,
    }
    if thread != "main" or summary != "fixture-data":
        return TemporalOracleResult(
            conclusion="inconclusive",
            observation=observation,
            rationale="The captured event does not bind the expected main-thread weather call.",
        )
    if delay_ms > 0 and latency_ms >= threshold_ms:
        return TemporalOracleResult(
            conclusion="locally_supported",
            observation=observation,
            rationale="The delayed dependency produced a bounded but over-budget main-thread call.",
        )
    return TemporalOracleResult(
        conclusion="locally_rejected",
        observation=observation,
        rationale="The matched observation stayed within the preregistered temporal budget.",
    )


def execute_admitted_lanes(
    admission: RuntimeProbeAdmission,
    *,
    repo_root: str | Path,
    device: str,
    artifact_root: str | Path,
    model: str | None = None,
    command_runner: CommandRunner | None = None,
) -> tuple[Mapping[str, Any], ...]:
    """Execute each admitted lane once through the existing runner contracts.

    The function deliberately performs no implicit retry.  A lane that cannot
    produce an accountable terminal ExecutionRecord is returned as aborted and
    remains outside the formal denominator.  The temporal oracle is evaluated
    only after the runner has finalized both the ExecutionRecord and effective
    execution provenance.
    """

    if not admission.admitted or not admission.formal_denominator:
        raise RuntimeProbeError(("formal lanes require an admitted runtime probe",))
    root = Path(repo_root).resolve()
    artifacts = Path(artifact_root).resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    runner = command_runner or SubprocessCommandRunner()
    build = admission.manifest.document["build"]
    variants = {str(item["cell_id"]): item for item in build["variants"]}
    snapshots = {str(item["cell_id"]): Path(str(item["path"])) for item in admission.apk_snapshots}
    expected_apks = {str(lane["cell_id"]): str(lane["apk"]["sha256"]) for lane in admission.lanes}
    if set(snapshots) != set(expected_apks):
        raise RuntimeProbeError(("admission is missing immutable APK snapshots",))
    run_specs = {
        str(item["cell_id"]): root / str(item["path"])
        for item in admission.manifest.document["run_specs"]
    }
    results: list[Mapping[str, Any]] = []

    # Import lazily so loading/admitting a manifest remains independent of the
    # full runner's optional Codex/Android integrations.
    from aiverify.runner.cli import run as run_spec
    from aiverify.runner.execution_record import load_execution_record
    from aiverify.runner.run_spec import load_run_spec

    built_cells: dict[str, Mapping[str, Any]] = {}
    for lane in admission.lanes:
        cell_id = str(lane["cell_id"])
        lane_id = str(lane["lane_id"])
        variant = variants[cell_id]
        apk = root / str(build["host_project"]) / str(build["apk_relpath"])
        if cell_id not in built_cells:
            snapshot = snapshots[cell_id]
            if not snapshot.is_file() or _sha256_file(snapshot) != expected_apks[cell_id]:
                built_cells[cell_id] = {
                    "status": "invalid",
                    "reason": "admitted_snapshot_missing_or_changed",
                }
            else:
                apk.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(snapshot, apk)
                built_cells[cell_id] = {
                    "status": "ready",
                    "snapshot": str(snapshot),
                    "apk_sha256": _sha256_file(apk),
                }
        build_receipt = built_cells[cell_id]
        if build_receipt.get("status") != "ready":
            results.append(
                {
                    "lane_id": lane_id,
                    "cell_id": cell_id,
                    "repetition": lane["repetition"],
                    "status": "aborted",
                    "formal_denominator": False,
                    "attempts": 1,
                    "build": dict(build_receipt),
                    "reason": str(build_receipt.get("reason")),
                }
            )
            continue

        lane_dir = artifacts / lane_id
        spec_path = run_specs[cell_id]
        try:
            # The existing runner's live-validation gate intentionally runs
            # before its identity deployment.  Stage the already-admitted APK
            # once so that gate can prove the package/activity surface; the
            # runner then performs its authoritative identity-bound deployment.
            preinstall_command = [
                str(admission.manifest.document["tool_policy"]["android_cli"]["binary"]),
                "run",
                f"--device={device}",
                f"--apks={apk}",
                f"--activity={variant['activity']}",
                "--type=ACTIVITY",
            ]
            preinstall_started = time.monotonic()
            preinstall = runner.run(
                preinstall_command,
                cwd=root,
                timeout_seconds=int(build["timeout_seconds"]),
            )
            preinstall_receipt = {
                "command": preinstall_command,
                "returncode": preinstall.returncode,
                "seconds": round(time.monotonic() - preinstall_started, 3),
                "stdout_tail": preinstall.stdout[-2000:],
                "stderr_tail": preinstall.stderr[-2000:],
            }
            lane_dir.mkdir(parents=True, exist_ok=True)
            _write_new_json(lane_dir / "admission-deployment.json", preinstall_receipt)
            if preinstall.returncode != 0:
                results.append(
                    {
                        "lane_id": lane_id,
                        "cell_id": cell_id,
                        "repetition": lane["repetition"],
                        "status": "aborted",
                        "formal_denominator": False,
                        "attempts": 1,
                        "build": dict(build_receipt),
                        "admission_deployment": preinstall_receipt,
                        "reason": "admission_deployment_failed",
                    }
                )
                continue
            # The Run Spec's portable relative host_project resolves to the
            # same repository root; do not override it with a non-structured
            # locator (the parser deliberately rejects that ambiguity).
            spec = load_run_spec(spec_path)
            verdict = run_spec(
                spec,
                device=device,
                artifact_dir=lane_dir / "artifacts",
                workdir=root,
                model=model,
                run_spec_path=spec_path,
            )
            record_path = lane_dir / "execution-record.json"
            provenance_path = lane_dir / "execution-provenance.json"
            record = load_execution_record(record_path)
            identity_complete = provenance_path.is_file()
            accountable = (
                record["lifecycle_state"] == "completed"
                and record["execution"]["accounting_eligible"] is True
                and identity_complete
            )
            if not accountable:
                results.append(
                    {
                        "lane_id": lane_id,
                        "cell_id": cell_id,
                        "repetition": lane["repetition"],
                        "status": "aborted",
                        "formal_denominator": False,
                        "attempts": 1,
                        "build": dict(build_receipt),
                        "execution_record": str(record_path),
                        "execution_record_state": record["lifecycle_state"],
                        "reason": "non_accountable_execution_record",
                    }
                )
                continue
            logcat = "\n".join(
                path.read_text(encoding="utf-8")
                for path in sorted((lane_dir / "artifacts").glob("**/logcat.txt"))
            )
            oracle = evaluate_temporal_oracle(
                logcat,
                threshold_ms=int(admission.manifest.document["oracle"]["threshold_ms"]),
            )
            oracle_path = lane_dir / "oracle.json"
            _write_new_json(oracle_path, oracle.to_dict())
            checksums_path = lane_dir / "checksums.sha256"
            _write_checksums(checksums_path, lane_dir)
            results.append(
                {
                    "lane_id": lane_id,
                    "cell_id": cell_id,
                    "repetition": lane["repetition"],
                    "status": "completed",
                    "formal_denominator": True,
                    "attempts": 1,
                    "oracle": oracle.to_dict(),
                    "execution_record": str(record_path),
                    "execution_identity": str(provenance_path),
                    "verdict": str(lane_dir / "verdict.json"),
                    "checksums": str(checksums_path),
                    "runner_execution": verdict.get("execution", {}),
                }
            )
        except Exception as error:  # noqa: BLE001 - lane must fail closed without retry
            # The lane is terminally aborted; this branch intentionally does
            # not retry or turn a partial artifact into an accountable result.
            results.append(
                {
                    "lane_id": lane_id,
                    "cell_id": cell_id,
                    "repetition": lane["repetition"],
                    "status": "aborted",
                    "formal_denominator": False,
                    "attempts": 1,
                    "reason": "lane_execution_error",
                    "error": f"{type(error).__name__}: {error}",
                }
            )
    return tuple(results)


def _manifest_errors(document: Mapping[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    policy = document["policy"]
    cells = document["cells"]
    if int(policy["planned_lanes"]) != 6:
        errors.append("policy.planned_lanes must be exactly 6")
    if int(policy["repetitions_per_cell"]) != 3:
        errors.append("policy.repetitions_per_cell must be exactly 3")
    if [str(cell["cell_id"]) for cell in cells] != ["change-defect", "change-control"]:
        errors.append("cells must be ordered change-defect then change-control")
    if any(int(cell["repetitions"]) != 3 for cell in cells):
        errors.append("each cell must have three repetitions")
    if policy["max_attempts_per_lane"] != 1 or policy["no_retry_after_accountable"] is not True:
        errors.append("runtime lanes permit one attempt and no retry after accountability")
    if document["claim_boundary"]["local_only"] is not True:
        errors.append("claim boundary must remain local-only")
    for artifact in (
        *document["source_identity"]["source_files"],
        document["source_identity"]["context_manifest"],
        document["source_identity"]["change_input"],
    ):
        if not _SHA256.fullmatch(str(artifact["sha256"])):
            errors.append(f"invalid sha256 for {artifact['path']}")
    if document["oracle"]["threshold_ms"] <= 0:
        errors.append("oracle.threshold_ms must be positive")
    return tuple(errors)


def _check_device(target: Mapping[str, Any], runner: CommandRunner) -> tuple[list[Mapping[str, Any]], list[str]]:
    checks: list[Mapping[str, Any]] = []
    reasons: list[str] = []
    serial = str(target["serial"])
    result = runner.run([str(target["adb_binary"]), "-s", serial, "get-state"], timeout_seconds=30)
    online = result.returncode == 0 and result.stdout.strip() == "device"
    checks.append({"name": "device_online", "status": "pass" if online else "fail", "detail": _command_detail(result)})
    if not online:
        reasons.append("device_unavailable")
        return checks, reasons
    for name, prop, expected in (
        ("device_api", "ro.build.version.sdk", str(target["api_level"])),
        ("device_model", "ro.product.model", str(target["model"])),
        ("device_avd", "ro.boot.qemu.avd_name", str(target["avd"])),
    ):
        result = runner.run([str(target["adb_binary"]), "-s", serial, "shell", "getprop", prop], timeout_seconds=30)
        passed = result.returncode == 0 and result.stdout.strip() == expected
        checks.append({"name": name, "status": "pass" if passed else "fail", "detail": f"expected={expected} actual={result.stdout.strip()}"})
        if not passed:
            reasons.append(f"{name}_mismatch")
    # Runtime admission uses a static no-INTERNET-permission proof below.  We
    # intentionally do not toggle airplane mode or Wi-Fi from this read-only
    # target inspection; the runner never grants the app a network capability.
    checks.append({
        "name": "network_policy",
        "status": "deferred",
        "detail": "requires APK manifest permission proof",
    })
    return checks, reasons


def _apk_metadata(apk: Path, *, package: str, activity: str) -> tuple[bool, str]:
    result = subprocess.run(
        ["apkanalyzer", "manifest", "print", str(apk)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        return False, result.stderr.strip() or "apkanalyzer failed"
    try:
        root = ET.fromstring(result.stdout)
    except ET.ParseError as error:
        return False, f"manifest parse failed: {error}"
    namespace = "{http://schemas.android.com/apk/res/android}"
    actual_package = root.attrib.get("package")
    activities = {
        item.attrib.get(namespace + "name")
        for item in root.iter("activity")
    }
    return (
        actual_package == package and activity in activities,
        f"package={actual_package} activities={sorted(item for item in activities if item)}",
    )


def _apk_network_policy(apk: Path) -> tuple[bool, str]:
    """Prove this fixture cannot make network calls without INTERNET permission."""

    result = subprocess.run(
        ["apkanalyzer", "manifest", "permissions", str(apk)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        return False, result.stderr.strip() or "permission inspection failed"
    permissions = tuple(line.strip() for line in result.stdout.splitlines() if line.strip())
    allowed = "android.permission.INTERNET" not in permissions
    return allowed, f"permissions={list(permissions)}"


def _write_new_json(path: Path, document: Mapping[str, Any]) -> None:
    if path.exists():
        raise RuntimeProbeError((f"refusing to overwrite evidence: {path}",))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_checksums(path: Path, root: Path) -> None:
    if path.exists():
        raise RuntimeProbeError((f"refusing to overwrite checksums: {path}",))
    lines = []
    for candidate in sorted(item for item in root.rglob("*") if item.is_file() and item != path):
        lines.append(f"{_sha256_file(candidate)}  {candidate.relative_to(root).as_posix()}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeProbeError((f"duplicate JSON key: {key}",))
        result[key] = value
    return result


def _canonical_bytes(document: Mapping[str, Any]) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _command_detail(result: CommandResult) -> str:
    output = (result.stdout or result.stderr).strip().replace("\n", " | ")
    return f"exit={result.returncode} {output[-500:]}".strip()


def _render_schema_error(error: Any) -> str:
    path = ".".join(str(item) for item in error.absolute_path)
    return f"{path + ': ' if path else ''}{error.message}"
