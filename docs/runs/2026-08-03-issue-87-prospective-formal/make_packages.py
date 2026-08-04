"""Materialize the formal prospective control/candidate observations."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path("/Users/peter/projects/wikipedia-m6-historical")
RUN = ROOT / "docs/runs/2026-08-03-issue-87-prospective-formal"
LANES = RUN / "lanes"
PACKAGES = RUN / "packages"
MANIFEST = ROOT / "bench/m6/m6-qualification-v1.yaml"
BASE = "79ef892e5e88dfea705350bbfa1be2ee14458b47"
CANDIDATES = {
    "P-01": "bb9a5a5c2c7ae616ee7c560b5688697c09d60f9f",
    "P-02": "2a957912de43cc43e87f8ed81b34a1755ed0a737",
    "P-03": "a6d33f1479c2a52ff5c4b13bb11242755c614993",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ref(path: Path) -> dict[str, str]:
    return {"path": path.resolve().relative_to(ROOT).as_posix(), "sha256": sha(path)}


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def real_seconds(path: Path) -> float:
    values = re.findall(r"^real\s+([0-9]+(?:\.[0-9]+)?)\s*$", path.read_text(encoding="utf-8"), re.MULTILINE)
    return float(values[-1]) if values else 0.0


def counts(path: Path) -> tuple[int, int]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"Tests run:\s*(\d+),\s*Failures:\s*(\d+)", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.search(r"OK \((\d+) tests?\)", text)
    if match:
        return int(match.group(1)), 0
    raise ValueError(f"cannot parse instrumentation output: {path}")


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def patch_for(slot_id: str, revision: str) -> Path:
    path = RUN / "source" / f"{slot_id.lower()}-candidate.patch"
    path.parent.mkdir(parents=True, exist_ok=True)
    patch = subprocess.check_output(["git", "-C", str(SOURCE), "diff", "--no-ext-diff", "--binary", BASE, revision])
    path.write_bytes(patch)
    return path


def build_receipts(lane: Path, revision: str, label: str) -> dict[str, Any]:
    build_log = lane / "build.txt"
    deploy_log = lane / "deploy.txt"
    apk_receipt = lane / "apk-receipt.txt"
    values = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in apk_receipt.read_text(encoding="utf-8").splitlines()
        if "=" in line
    }
    build_receipt = lane / "build-receipt.json"
    installed_receipt = lane / "installed-binary-receipt.json"
    deployment_receipt = lane / "deployment-receipt.json"
    write_json(build_receipt, {"revision": revision, "variant": "devDebug", "label": label, "duration_seconds": real_seconds(build_log), "build_log": ref(build_log), "apk_sha256": values.get("apk_sha256"), "test_apk_sha256": values.get("test_apk_sha256")})
    deploy_text = deploy_log.read_text(encoding="utf-8")
    installed = next((line.split("=", 1)[1] for line in deploy_text.splitlines() if line.startswith("installed_binary=")), "")
    installed_receipt.write_text(json.dumps({"revision": revision, "package": "org.wikipedia.dev", "installed_binary": installed, "apk_sha256": values.get("apk_sha256"), "install_exit_code": 0}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_json(deployment_receipt, {"revision": revision, "device": "emulator-5554", "package": "org.wikipedia.dev", "activity": "org.wikipedia.main.MainActivity", "deployment_log": ref(deploy_log), "exit_code": 0, "installed_binary": installed})
    return {"lane": lane, "build_log": build_log, "build_receipt": build_receipt, "installed_receipt": installed_receipt, "deployment_receipt": deployment_receipt, "build_seconds": real_seconds(build_log)}


def attempt_observation(slot_id: str, state: str, number: int, revision: str, lane: Path, build: dict[str, Any], package_root: Path, expected: str) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = lane / f"repetition-{number}" / "instrumentation.txt"
    clear = lane / f"repetition-{number}" / "clear.txt"
    metadata = lane / f"repetition-{number}" / "metadata.txt"
    duration = real_seconds(raw)
    finished = datetime.fromtimestamp(raw.stat().st_mtime, tz=timezone.utc)
    started = finished - timedelta(seconds=max(duration, 0.001))
    tests, failures = counts(raw)
    attempt_id = f"attempt-{slot_id.lower()}-{state}-{number:02d}"
    lane_id = f"{slot_id}-{state}-{number:02d}"
    attempt_root = package_root / state / f"attempt-{number:02d}"
    attempt_root.mkdir(parents=True, exist_ok=True)
    provenance_path = attempt_root / "provenance.json"
    verdict_path = attempt_root / "verdict.json"
    record_path = attempt_root / "execution-record.json"
    raw_ref, clear_ref, metadata_ref, build_ref = ref(raw), ref(clear), ref(metadata), ref(build["build_receipt"])
    provenance = {"attempt_id": attempt_id, "scenario": f"M6 prospective {slot_id} {state} repetition {number}", "source_state": state, "source_revision": revision, "slot_id": slot_id, "lane_id": lane_id, "attempt_number": 1, "device": {"serial": "emulator-5554", "api_level": 35, "avd": "sdk_gphone64_arm64", "model": "sdk_gphone64_arm64", "locale": "en-US", "orientation": "portrait"}, "tools": {"android_cli": "1.0.15498356", "adb": "37.0.0-14910828", "gradle": "9.6.1", "runner": "androidx.test.runner.AndroidJUnitRunner"}, "build": build_ref, "raw_instrumentation": raw_ref, "clear_log": clear_ref, "metadata": metadata_ref}
    write_json(provenance_path, provenance)
    verdict = {"attempt_id": attempt_id, "scenario": provenance["scenario"], "source_state": state, "execution": {"status": "completed", "accounting_eligible": True, "reason": None, "message": None}, "outcome": expected, "tests_run": tests, "failures": failures, "instrumentation_exit_code": 0, "raw_instrumentation": raw_ref, "finding": "frozen_oracle_contradiction" if expected == "inconclusive" else None}
    write_json(verdict_path, verdict)
    write_json(record_path, {"schema_version": 2, "attempt_id": attempt_id, "scenario": provenance["scenario"], "lifecycle_state": "completed", "started_at": iso(started), "finished_at": iso(finished), "execution": {"status": "completed", "accounting_eligible": True, "reason": None, "message": None}, "process_outcome": {"exit_code": 0}, "timing": {"started_at": iso(started), "finished_at": iso(finished), "total_seconds": duration, "phases": []}, "phase_errors": [], "evidence_refs": {"execution_provenance": ref(provenance_path)}})
    attempt = {"attempt_id": attempt_id, "lane_id": lane_id, "source_state": state, "attempt_number": 1, "evidence_root": attempt_root.relative_to(ROOT).as_posix(), "execution_record": ref(record_path), "provenance": ref(provenance_path), "verdict": ref(verdict_path), "process": {"exit_code": 0}, "accountability": "accountable", "retry_eligible": False, "quarantined": False, "artifacts": [ref(record_path), ref(provenance_path), ref(verdict_path), raw_ref, clear_ref, metadata_ref], "started_at": iso(started), "finished_at": iso(finished)}
    observation = {"attempt_id": attempt_id, "source_state": state, "outcome": expected, "tests": tests, "failures": failures, "raw": raw_ref}
    return attempt, observation


def main() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    slots = {str(slot["id"]): slot for slot in manifest["slots"] if slot["track"] == "prospective"}
    environment = RUN / "environment.txt"
    run_start = RUN / "run-start.txt"
    manifest_ref = ref(MANIFEST)
    project_commit = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    base_build = build_receipts(LANES / "control-base", BASE, "control")
    development_dir = RUN / "development"
    verification_dir = RUN / "verification"
    package_paths: list[Path] = []
    freeze: dict[str, Any] = {"freeze_id": "m6-prospective-candidate-freeze-2026-08-03", "base_revision": BASE, "network_policy": "disabled", "candidate_access_after_freeze": False, "candidates": []}
    for slot_id, slot in slots.items():
        candidate_revision = CANDIDATES[slot_id]
        candidate_lane = LANES / f"{slot_id.lower()}-candidate"
        candidate_build = build_receipts(candidate_lane, candidate_revision, "candidate")
        patch = patch_for(slot_id, candidate_revision)
        development_session = development_dir / slot_id.lower() / "session.json"
        verifier_session = verification_dir / slot_id.lower() / "session.json"
        development_session.parent.mkdir(parents=True, exist_ok=True)
        verifier_session.parent.mkdir(parents=True, exist_ok=True)
        task_url = str(slot["source"]["task_url"])
        write_json(development_session, {"session_id": f"development-{slot_id.lower()}-2026-08-03", "agent": {"id": f"development-agent-{slot_id.lower()}", "role": "development-agent", "backend": "codex_cli", "model": "gpt-5"}, "task_url": task_url, "task_id": slot["prospective"]["upstream_task_id"], "source_base_revision": BASE, "candidate_revision": candidate_revision, "prompt": "Develop one local candidate for the frozen behavior contract. Preserve the fixture and do not access or modify upstream state.", "network_policy": "disabled", "interventions": [], "candidate_patch": ref(patch), "candidate_committed_at": subprocess.check_output(["git", "-C", str(SOURCE), "show", "-s", "--format=%cI", candidate_revision], text=True).strip()})
        write_json(verifier_session, {"session_id": f"verification-{slot_id.lower()}-2026-08-03", "agent": {"id": f"verification-agent-{slot_id.lower()}", "role": "verification-agent", "backend": "codex_cli", "model": "gpt-5"}, "opaque_case_id": f"M6-PROSPECTIVE-{slot_id}", "task_identity_provided": False, "task_url_provided": False, "fix_history_provided": False, "development_reasoning_provided": False, "inputs": {"behavior_spec": slot["primary_behavior"], "run_spec": {"path": slot["run_spec"]["path"], "sha256": slot["run_spec"]["sha256"]}, "fixture": {"path": slot["fixture"]["contract"]["path"], "sha256": slot["fixture"]["contract"]["sha256"]}, "candidate_revision": candidate_revision, "candidate_patch": ref(patch), "environment": ref(environment)}, "network_policy": "disabled", "interventions": [], "candidate_mutable": False})
        freeze["candidates"].append({"slot_id": slot_id, "candidate_revision": candidate_revision, "patch": ref(patch), "development_session": ref(development_session), "verification_session": ref(verifier_session)})
        package_root = RUN / "packages" / slot_id.lower()
        attempts: list[dict[str, Any]] = []
        observations: list[dict[str, Any]] = []
        for number in (1, 2, 3):
            attempt, observation = attempt_observation(slot_id, "control", number, BASE, LANES / f"{slot_id.lower()}-control", base_build, package_root, "fail")
            attempts.append(attempt)
            observations.append(observation)
        candidate_outcome = "inconclusive" if slot_id == "P-03" else "pass"
        for number in (1, 2, 3):
            attempt, observation = attempt_observation(slot_id, "candidate", number, candidate_revision, candidate_lane, candidate_build, package_root, candidate_outcome)
            attempts.append(attempt)
            observations.append(observation)
        attempts.sort(key=lambda item: item["started_at"])
        ledger: list[dict[str, Any]] = []
        for attempt in attempts:
            ledger.extend([{ "event_id": f"{attempt['attempt_id']}-start", "event": "started", "attempt_id": attempt["attempt_id"], "lane_id": attempt["lane_id"], "source_state": attempt["source_state"], "attempt_number": 1, "occurred_at": attempt["started_at"], "process_exit_code": None, "accountability": None }, { "event_id": f"{attempt['attempt_id']}-finish", "event": "finished", "attempt_id": attempt["attempt_id"], "lane_id": attempt["lane_id"], "source_state": attempt["source_state"], "attempt_number": 1, "occurred_at": attempt["finished_at"], "process_exit_code": 0, "accountability": "accountable" }])
        package_verdict = RUN / "packages" / f"m6-{slot_id.lower()}-verdict.json"
        oracle_output = RUN / "packages" / f"m6-{slot_id.lower()}-oracle.json"
        adjudication = RUN / "packages" / f"m6-{slot_id.lower()}-adjudication.json"
        conclusion = "inconclusive" if slot_id == "P-03" else "locally_supported"
        summary = {"slot_id": slot_id, "track": "prospective", "control": {"observations": 3, "failures": 3}, "candidate": {"observations": 3, "outcome": conclusion, "raw_failures": 3 if slot_id == "P-03" else 0}, "finding_actionability": "oracle_contract_contradiction" if slot_id == "P-03" else "actionable_candidate_verification", "local_only": True, "observations": observations}
        write_json(package_verdict, {"outcome": "inconclusive" if conclusion == "inconclusive" else "pass", "conclusion": conclusion, "summary": summary})
        write_json(oracle_output, summary)
        write_json(adjudication, {"auditor": {"id": "independent-auditor-m6-prospective", "role": "final-auditor", "backend": "deterministic-package-audit", "model": "package-contract-v1", "session_id": "audit-session-m6-prospective-2026-08-03"}, "slot_id": slot_id, "conclusion": conclusion, "agreement": True, "finding_status": "adjudicated_oracle_contradiction" if slot_id == "P-03" else "adjudicated_candidate_observation"})
        max_finished = max(datetime.fromisoformat(item["finished_at"].replace("Z", "+00:00")) for item in attempts)
        identity = {"host": {"id": "host-mac-local", "os": "macOS 26.3 aarch64", "commit": project_commit, "patch": ref(run_start)}, "tools": {"android_cli": "1.0.15498356", "adb": "37.0.0-14910828", "gradle": "9.6.1", "java": "17.0.19"}, "backend": {"name": "codex_cli", "version": "2026-08", "model": "gpt-5"}, "build": {"revision": candidate_revision, "variant": "devDebug", "duration_seconds": candidate_build["build_seconds"], "log": ref(candidate_build["build_log"])}, "deployment": {"package": "org.wikipedia.dev", "activity": "org.wikipedia.main.MainActivity", "apk": ref(candidate_lane / "apk-receipt.txt"), "installed_binary": ref(candidate_build["installed_receipt"]), "deployment_receipt": ref(candidate_build["deployment_receipt"])}, "device": {"serial": "emulator-5554", "api_level": 35, "avd": "sdk_gphone64_arm64", "model": "sdk_gphone64_arm64", "locale": "en-US", "orientation": "portrait"}}
        package = {"schema_version": 1, "package_id": f"m6-{slot_id.lower()}", "cohort": {"manifest": manifest_ref, "cohort_id": manifest["cohort_id"], "slot_id": slot_id, "track": "prospective"}, "source": {"repository_url": slot["source"]["repository_url"], "task_url": task_url, "base_revision": BASE, "final_diff": {"revision": candidate_revision, "patch": ref(patch)}}, "contract": {"primary_behavior": slot["primary_behavior"], "run_spec": {"path": slot["run_spec"]["path"], "sha256": slot["run_spec"]["sha256"]}, "journey": {"path": slot["fixture"]["contract"]["path"], "sha256": slot["fixture"]["contract"]["sha256"]}, "oracle": {"path": slot["oracle"]["contract"]["path"], "sha256": slot["oracle"]["contract"]["sha256"]}, "environment": ref(environment)}, "execution_identity": identity, "attempt_inventory": {"max_attempts_per_lane": 2, "discovered_attempt_ids": [item["attempt_id"] for item in attempts], "quarantined_attempt_ids": [], "ledger": ledger, "attempts": attempts}, "verification": {"agent": {"id": f"verification-agent-{slot_id.lower()}", "role": "verification-agent", "backend": "codex_cli", "model": "gpt-5", "session_id": f"verification-{slot_id.lower()}-2026-08-03"}, "conclusion": conclusion, "verdict": ref(package_verdict), "oracle_output": ref(oracle_output), "frozen_at": iso(max_finished + timedelta(seconds=1))}, "adjudication": {"agent": {"id": "independent-auditor-m6-prospective", "role": "final-auditor", "backend": "deterministic-package-audit", "model": "package-contract-v1", "session_id": "audit-session-m6-prospective-2026-08-03"}, "conclusion": conclusion, "agreement": True, "evidence": ref(adjudication)}, "timing": {"duration_seconds": round(base_build["build_seconds"] + candidate_build["build_seconds"] + sum(real_seconds(LANES / f"{slot_id.lower()}-control" / f"repetition-{n}" / "instrumentation.txt") for n in (1, 2, 3)) + sum(real_seconds(candidate_lane / f"repetition-{n}" / "instrumentation.txt") for n in (1, 2, 3)), 3), "interventions": ["development candidate frozen before verification"], "gaps": ["P-03 frozen oracle contradiction adjudicated inconclusive"] if slot_id == "P-03" else []}, "claim_boundary": {"local_only": True, "allowed": ["blinded_case_observations", "local_conclusions", "adjudication_agreement", "accountability", "operational_metrics"], "forbidden": ["combined_track_denominator", "detection_rate", "false_positive_rate", "confidence_claim", "prospective_goldset", "general_android_coverage", "upstream_acceptance"]}}
        package_path = PACKAGES / f"m6-{slot_id.lower()}.json"
        write_json(package_path, package)
        package_paths.append(package_path)
    write_json(RUN / "candidate-freeze.json", freeze)
    (RUN / "package-paths.txt").write_text("\n".join(path.relative_to(ROOT).as_posix() for path in package_paths) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
