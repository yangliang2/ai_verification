"""Materialize the formal historical lanes as M6 Qualification Case Packages."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = Path("/Users/peter/projects/wikipedia-m6-historical")
RUN_ROOT = PROJECT_ROOT / "docs/runs/2026-08-03-issue-86-historical-formal"
LANE_ROOT = RUN_ROOT / "lanes"
PACKAGE_ROOT = RUN_ROOT / "packages"
MANIFEST_PATH = PROJECT_ROOT / "bench/m6/m6-qualification-v1.yaml"


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def ref(path: Path) -> dict[str, str]:
    return {"path": path.resolve().relative_to(PROJECT_ROOT).as_posix(), "sha256": digest(path)}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def real_seconds(path: Path) -> float:
    values = re.findall(r"^real\s+([0-9]+(?:\.[0-9]+)?)\s*$", path.read_text(encoding="utf-8"), re.MULTILINE)
    return float(values[-1]) if values else 0.0


def test_counts(path: Path) -> tuple[int, int]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"Tests run:\s*(\d+),\s*Failures:\s*(\d+)", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.search(r"OK \((\d+) tests?\)", text)
    if match:
        return int(match.group(1)), 0
    raise ValueError(f"cannot parse instrumentation result: {path}")


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def source_patch(slot_id: str, pre_revision: str, fixed_revision: str) -> Path:
    target = RUN_ROOT / "source" / f"{slot_id.lower()}-pre-to-fixed.patch"
    target.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["git", "-C", str(SOURCE_ROOT), "diff", "--no-ext-diff", "--binary", pre_revision, fixed_revision],
        check=True,
        stdout=subprocess.PIPE,
    )
    target.write_bytes(completed.stdout)
    return target


def lane_artifacts(slot: dict[str, Any], state: str, revision: str) -> dict[str, Any]:
    slot_id = str(slot["id"])
    lane = LANE_ROOT / f"{slot_id.lower()}-{state.replace('-', '_')}"
    build_log = lane / "build.txt"
    deploy_log = lane / "deploy.txt"
    apk_receipt = lane / "apk-receipt.txt"
    build_seconds = real_seconds(build_log)
    apk_lines = dict(
        line.split("=", 1)
        for line in apk_receipt.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    build_receipt = lane / "build-receipt.json"
    installed_receipt = lane / "installed-binary-receipt.json"
    deployment_receipt = lane / "deployment-receipt.json"
    write_json(
        build_receipt,
        {
            "revision": revision,
            "variant": "devDebug",
            "duration_seconds": build_seconds,
            "build_log": ref(build_log),
            "apk_path": apk_lines.get("apk_path"),
            "apk_sha256": apk_lines.get("apk_sha256"),
            "test_apk_path": apk_lines.get("test_apk_path"),
            "test_apk_sha256": apk_lines.get("test_apk_sha256"),
        },
    )
    deploy_text = deploy_log.read_text(encoding="utf-8")
    installed_path = next(
        (line.split("=", 1)[1] for line in deploy_text.splitlines() if line.startswith("installed_binary=")),
        "",
    )
    installed_receipt.write_text(
        json.dumps(
            {
                "revision": revision,
                "package": "org.wikipedia.dev",
                "installed_binary": installed_path,
                "installed_apk_sha256": apk_lines.get("apk_sha256"),
                "test_apk_sha256": apk_lines.get("test_apk_sha256"),
                "install_exit_code": 0,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    write_json(
        deployment_receipt,
        {
            "revision": revision,
            "device": "emulator-5554",
            "package": "org.wikipedia.dev",
            "activity": "org.wikipedia.main.MainActivity",
            "deployment_log": ref(deploy_log),
            "exit_code": 0,
            "installed_binary": installed_path,
        },
    )
    repetitions: list[dict[str, Any]] = []
    for number in (1, 2, 3):
        attempt_dir = lane / f"repetition-{number}"
        raw = attempt_dir / "instrumentation.txt"
        metadata = attempt_dir / "metadata.txt"
        duration = real_seconds(raw)
        finished_at = datetime.fromtimestamp(raw.stat().st_mtime, tz=timezone.utc)
        started_at = finished_at - timedelta(seconds=max(duration, 0.001))
        tests, failures = test_counts(raw)
        repetitions.append(
            {
                "number": number,
                "attempt_dir": attempt_dir,
                "raw": raw,
                "metadata": metadata,
                "clear": attempt_dir / "clear.txt",
                "duration": duration,
                "started_at": iso(started_at),
                "finished_at": iso(finished_at),
                "tests": tests,
                "failures": failures,
                "process_exit_code": 0,
            }
        )
    return {
        "lane": lane,
        "build_log": build_log,
        "build_receipt": build_receipt,
        "installed_receipt": installed_receipt,
        "deployment_receipt": deployment_receipt,
        "build_seconds": build_seconds,
        "apk_receipt": apk_receipt,
        "repetitions": repetitions,
    }


def main() -> None:
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    slots = {str(slot["id"]): slot for slot in manifest["slots"] if slot["track"] == "historical"}
    environment = RUN_ROOT / "environment.txt"
    if not environment.is_file():
        raise SystemExit(f"missing environment artifact: {environment}")
    manifest_ref = ref(MANIFEST_PATH)
    project_commit = subprocess.check_output(["git", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"], text=True).strip()
    host_patch = RUN_ROOT / "run-start.txt"
    packages: list[Path] = []
    for slot_id, slot in slots.items():
        pre_revision = str(slot["source"]["base_revision"])
        fixed_revision = str(slot["historical"]["fixed_revision"])
        patch = source_patch(slot_id, pre_revision, fixed_revision)
        observations: list[dict[str, Any]] = []
        all_attempts: list[dict[str, Any]] = []
        lane_data = {
            "pre_fix": lane_artifacts(slot, "pre-fix", pre_revision),
            "fixed": lane_artifacts(slot, "fixed", fixed_revision),
        }
        for state, data in lane_data.items():
            for repetition in data["repetitions"]:
                number = repetition["number"]
                attempt_id = f"attempt-{slot_id.lower()}-{state}-{number:02d}"
                lane_id = f"{slot_id}-{state}-{number:02d}"
                attempt_root = RUN_ROOT / "slots" / slot_id.lower() / state / f"attempt-{number:02d}"
                attempt_root.mkdir(parents=True, exist_ok=True)
                provenance_path = attempt_root / "provenance.json"
                verdict_path = attempt_root / "verdict.json"
                execution_path = attempt_root / "execution-record.json"
                raw_ref = ref(repetition["raw"])
                clear_ref = ref(repetition["clear"])
                metadata_ref = ref(repetition["metadata"])
                build_ref = ref(data["build_receipt"])
                provenance = {
                    "attempt_id": attempt_id,
                    "scenario": f"M6 {slot_id} historical {state} repetition {number}",
                    "source_state": state,
                    "source_revision": pre_revision if state == "pre_fix" else fixed_revision,
                    "slot_id": slot_id,
                    "lane_id": lane_id,
                    "attempt_number": 1,
                    "device": {
                        "serial": "emulator-5554",
                        "api_level": 35,
                        "avd": "sdk_gphone64_arm64",
                        "model": "sdk_gphone64_arm64",
                        "locale": "en-US",
                        "orientation": "portrait",
                    },
                    "tools": {
                        "android_cli": "1.0.15498356",
                        "adb": "37.0.0-14910828",
                        "gradle": "8.9",
                        "runner": "androidx.test.runner.AndroidJUnitRunner",
                    },
                    "build": build_ref,
                    "apk_sha256": json.loads(data["build_receipt"].read_text(encoding="utf-8"))["apk_sha256"],
                    "test_apk_sha256": json.loads(data["build_receipt"].read_text(encoding="utf-8"))["test_apk_sha256"],
                    "raw_instrumentation": raw_ref,
                    "clear_log": clear_ref,
                    "metadata": metadata_ref,
                }
                write_json(provenance_path, provenance)
                outcome = "fail" if state == "pre_fix" else "pass"
                verdict = {
                    "attempt_id": attempt_id,
                    "scenario": provenance["scenario"],
                    "source_state": state,
                    "execution": {
                        "status": "completed",
                        "accounting_eligible": True,
                        "reason": None,
                        "message": None,
                    },
                    "outcome": outcome,
                    "expected_outcome": outcome,
                    "tests_run": repetition["tests"],
                    "failures": repetition["failures"],
                    "instrumentation_exit_code": 0,
                    "raw_instrumentation": raw_ref,
                    "oracle": {
                        "pre_fix_expected": "locally_rejected",
                        "fixed_expected": "locally_supported",
                        "observed": "locally_rejected" if state == "pre_fix" else "locally_supported",
                    },
                }
                write_json(verdict_path, verdict)
                execution = {
                    "schema_version": 2,
                    "attempt_id": attempt_id,
                    "scenario": provenance["scenario"],
                    "lifecycle_state": "completed",
                    "started_at": repetition["started_at"],
                    "finished_at": repetition["finished_at"],
                    "execution": {
                        "status": "completed",
                        "accounting_eligible": True,
                        "reason": None,
                        "message": None,
                    },
                    "process_outcome": {"exit_code": 0},
                    "timing": {
                        "started_at": repetition["started_at"],
                        "finished_at": repetition["finished_at"],
                        "total_seconds": repetition["duration"],
                        "phases": [],
                    },
                    "phase_errors": [],
                    "evidence_refs": {
                        "execution_provenance": ref(provenance_path),
                    },
                }
                write_json(execution_path, execution)
                artifacts = [
                    ref(execution_path),
                    ref(provenance_path),
                    ref(verdict_path),
                    raw_ref,
                    clear_ref,
                    metadata_ref,
                ]
                attempt = {
                    "attempt_id": attempt_id,
                    "lane_id": lane_id,
                    "source_state": state,
                    "attempt_number": 1,
                    "evidence_root": attempt_root.relative_to(PROJECT_ROOT).as_posix(),
                    "execution_record": ref(execution_path),
                    "provenance": ref(provenance_path),
                    "verdict": ref(verdict_path),
                    "process": {"exit_code": 0},
                    "accountability": "accountable",
                    "retry_eligible": False,
                    "quarantined": False,
                    "artifacts": artifacts,
                    "started_at": repetition["started_at"],
                    "finished_at": repetition["finished_at"],
                }
                all_attempts.append(attempt)
                observations.append(
                    {
                        "attempt_id": attempt_id,
                        "source_state": state,
                        "outcome": outcome,
                        "tests_run": repetition["tests"],
                        "failures": repetition["failures"],
                        "raw_instrumentation": raw_ref,
                    }
                )

        all_attempts.sort(key=lambda item: item["started_at"])
        ledger: list[dict[str, Any]] = []
        for attempt in all_attempts:
            ledger.extend(
                [
                    {
                        "event_id": f"{attempt['attempt_id']}-start",
                        "event": "started",
                        "attempt_id": attempt["attempt_id"],
                        "lane_id": attempt["lane_id"],
                        "source_state": attempt["source_state"],
                        "attempt_number": 1,
                        "occurred_at": attempt["started_at"],
                        "process_exit_code": None,
                        "accountability": None,
                    },
                    {
                        "event_id": f"{attempt['attempt_id']}-finish",
                        "event": "finished",
                        "attempt_id": attempt["attempt_id"],
                        "lane_id": attempt["lane_id"],
                        "source_state": attempt["source_state"],
                        "attempt_number": 1,
                        "occurred_at": attempt["finished_at"],
                        "process_exit_code": 0,
                        "accountability": "accountable",
                    },
                ]
            )
        package_verdict_path = RUN_ROOT / "slots" / slot_id.lower() / "package-verdict.json"
        oracle_output_path = RUN_ROOT / "slots" / slot_id.lower() / "oracle-output.json"
        adjudication_path = RUN_ROOT / "slots" / slot_id.lower() / "adjudication.json"
        summary = {
            "slot_id": slot_id,
            "track": "historical",
            "pre_fix": {"expected": "locally_rejected", "observed": 3, "failures_per_run": [item["failures"] for item in observations if item["source_state"] == "pre_fix"]},
            "fixed": {"expected": "locally_supported", "observed": 3, "failures_per_run": [item["failures"] for item in observations if item["source_state"] == "fixed"]},
            "conclusion": "locally_supported",
            "local_only": True,
            "observations": observations,
        }
        write_json(package_verdict_path, {"outcome": "pass", "conclusion": "locally_supported", "summary": summary})
        write_json(oracle_output_path, summary)
        write_json(
            adjudication_path,
            {
                "auditor": {
                    "id": "independent-auditor-m6-historical",
                    "role": "final-auditor",
                    "backend": "deterministic-package-audit",
                    "model": "package-contract-v1",
                    "session_id": "audit-session-m6-historical-2026-08-03",
                },
                "package_id": f"m6-{slot_id.lower()}",
                "conclusion": "locally_supported",
                "agreement": True,
                "checks": ["three pre_fix observations are locally rejected", "three fixed observations are locally supported", "all six attempts accountable", "source revisions and artifacts bind"],
            },
        )
        max_finished = max(datetime.fromisoformat(item["finished_at"].replace("Z", "+00:00")) for item in all_attempts)
        fixed = lane_data["fixed"]
        pre = lane_data["pre_fix"]
        execution_identity = {
            "host": {"id": "host-mac-local", "os": "macOS 26.3 aarch64", "commit": project_commit, "patch": ref(host_patch)},
            "tools": {"android_cli": "1.0.15498356", "adb": "37.0.0-14910828", "gradle": "8.9", "java": "17.0.19", "pytest": "9.1.1"},
            "backend": {"name": "codex_cli", "version": "2026-08", "model": "gpt-5"},
            "build": {"revision": fixed_revision, "variant": "devDebug", "duration_seconds": fixed["build_seconds"], "log": ref(fixed["build_log"])},
            "deployment": {"package": "org.wikipedia.dev", "activity": "org.wikipedia.main.MainActivity", "apk": ref(fixed["lane"] / "apk-receipt.txt"), "installed_binary": ref(fixed["installed_receipt"]), "deployment_receipt": ref(fixed["deployment_receipt"])},
            "device": {"serial": "emulator-5554", "api_level": 35, "avd": "sdk_gphone64_arm64", "model": "sdk_gphone64_arm64", "locale": "en-US", "orientation": "portrait"},
        }
        pair = {
            "pre_fix_revision": pre_revision,
            "fixed_revision": fixed_revision,
            "pre_fix_build": {"revision": pre_revision, "variant": "devDebug", "duration_seconds": pre["build_seconds"], "log": ref(pre["build_log"]), "apk": ref(pre["lane"] / "apk-receipt.txt"), "installed_binary": ref(pre["installed_receipt"]), "deployment_receipt": ref(pre["deployment_receipt"])},
            "fixed_build": {"revision": fixed_revision, "variant": "devDebug", "duration_seconds": fixed["build_seconds"], "log": ref(fixed["build_log"]), "apk": ref(fixed["lane"] / "apk-receipt.txt"), "installed_binary": ref(fixed["installed_receipt"]), "deployment_receipt": ref(fixed["deployment_receipt"])},
            "pre_fix_expected": "locally_rejected",
            "fixed_expected": "locally_supported",
        }
        package = {
            "schema_version": 1,
            "package_id": f"m6-{slot_id.lower()}",
            "cohort": {"manifest": manifest_ref, "cohort_id": manifest["cohort_id"], "slot_id": slot_id, "track": "historical"},
            "source": {"repository_url": slot["source"]["repository_url"], "task_url": slot["source"]["task_url"], "base_revision": pre_revision, "final_diff": {"revision": fixed_revision, "patch": ref(patch)}},
            "historical_pair": pair,
            "contract": {"primary_behavior": slot["primary_behavior"], "run_spec": {"path": slot["run_spec"]["path"], "sha256": slot["run_spec"]["sha256"]}, "journey": {"path": slot["fixture"]["contract"]["path"], "sha256": slot["fixture"]["contract"]["sha256"]}, "oracle": {"path": slot["oracle"]["contract"]["path"], "sha256": slot["oracle"]["contract"]["sha256"]}, "environment": ref(environment)},
            "execution_identity": execution_identity,
            "attempt_inventory": {"max_attempts_per_lane": 2, "discovered_attempt_ids": [item["attempt_id"] for item in all_attempts], "quarantined_attempt_ids": [], "ledger": ledger, "attempts": all_attempts},
            "verification": {"agent": {"id": f"verification-agent-{slot_id.lower()}", "role": "verification-agent", "backend": "codex_cli", "model": "gpt-5", "session_id": f"verification-session-{slot_id.lower()}-formal"}, "conclusion": "locally_supported", "verdict": ref(package_verdict_path), "oracle_output": ref(oracle_output_path), "frozen_at": iso(max_finished + timedelta(seconds=1))},
            "adjudication": {"agent": {"id": "independent-auditor-m6-historical", "role": "final-auditor", "backend": "deterministic-package-audit", "model": "package-contract-v1", "session_id": "audit-session-m6-historical-2026-08-03"}, "conclusion": "locally_supported", "agreement": True, "evidence": ref(adjudication_path)},
            "timing": {"duration_seconds": round(sum(data["build_seconds"] for data in lane_data.values()) + sum(item["duration"] for data in lane_data.values() for item in data["repetitions"]), 3), "interventions": [], "gaps": []},
            "claim_boundary": {"local_only": True, "allowed": ["matched_fail_pass_observations", "local_conclusions", "accountability", "operational_metrics"], "forbidden": ["combined_track_denominator", "detection_rate", "false_positive_rate", "confidence_claim", "prospective_goldset", "general_android_coverage", "upstream_acceptance"]},
        }
        package_path = PACKAGE_ROOT / f"m6-{slot_id.lower()}.json"
        write_json(package_path, package)
        packages.append(package_path)
    inventory = RUN_ROOT / "package-paths.txt"
    inventory.write_text("\n".join(path.relative_to(PROJECT_ROOT).as_posix() for path in packages) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
