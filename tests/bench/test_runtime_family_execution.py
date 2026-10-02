"""End-to-end recording family execution from a real accepted preparation stage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from aiverify.bench import runtime_attempt, runtime_calibration, runtime_family_execution, runtime_family_preparation, runtime_mapping
from aiverify.bench.runtime_family_execution import RecordingLaneObservation
from aiverify.bench.runtime_attempt import RecordingDevicePolicy, verify_runtime_attempt
from tests.bench import test_runtime_family_preparation as preparation_fixture

CANDIDATE = preparation_fixture.CANDIDATE_ROOT
MAPPING = preparation_fixture.MAPPING_ROOT


def _prepared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, mapping_receipt: bool = False) -> Path:
    lanes, signer = preparation_fixture._family_inputs(tmp_path)

    def preparer(lane: runtime_family_preparation.RuntimeFamilyLaneInput):
        index = runtime_mapping.FROZEN_LANE_ORDER.index(lane.lane_id)
        apk = lane.options.artifact_dir / "build" / "app-debug.apk"
        apk.parent.mkdir(parents=True)
        payload = b"recording-control" if index % 2 == 0 else b"recording-defect"
        apk.write_bytes(payload)
        apk.chmod(0o444)
        receipt = preparation_fixture._receipt(
            lane, signer, apk, payload, lane.source_authority.mapping_binding,
        )
        document = receipt.receipt
        document["build"]["test_substitutes"] = True
        packed = preparation_fixture._repack_receipt(document)
        if mapping_receipt:
            return runtime_family_preparation.RuntimeFamilyLaneResult(receipt=packed.receipt)
        return packed

    root = tmp_path / "preparation"
    receipt = runtime_family_preparation.prepare_runtime_family(
        candidate_root=CANDIDATE, predecessor_root=MAPPING, output_root=root,
        lane_inputs=lanes, lane_preparer=preparer,
    )
    assert receipt.accepted, receipt.reason
    runtime_family_preparation.verify_runtime_family_preparation(receipt)
    assert all(any(artifact["kind"] == "raw_preparation_receipt" for artifact in row.artifacts) for row in receipt.rows)
    return root


def _policies(*, save: tuple[bool, ...] = (True, False, True, False)) -> tuple[RecordingLaneObservation, ...]:
    return tuple(RecordingLaneObservation(device=RecordingDevicePolicy(save_enabled=value)) for value in save)


def _execute(prep: Path, output: Path, *, observations: tuple[RecordingLaneObservation, ...] | None = None,
             session: runtime_family_execution.RecordingRuntimeFamilySession | None = None):
    return runtime_family_execution.execute_runtime_family(
        candidate_root=CANDIDATE, predecessor_root=prep, output_root=output,
        observations=observations if observations is not None else _policies(), session=session,
    )


def test_mapping_preparation_receipts_execute_four_lanes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prep = _prepared(tmp_path, monkeypatch, mapping_receipt=True)
    receipt = _execute(prep, tmp_path / "execution")
    assert receipt.accepted
    assert [row["status"] for row in receipt.document["rows"]] == ["accountable_concluded"] * 4
    for row in receipt.document["rows"]:
        assert verify_runtime_attempt(Path(row["receipt_path"]).parent)["verified"]


def _assert_no_terminal(output: Path) -> None:
    assert (output / "stage-start.json").is_file()
    assert not (output / "stage-terminal.json").exists()
    assert not (output / "family-execution.json").exists()


@pytest.mark.parametrize("mutation", ["candidate", "missing_predecessor", "terminal", "raw_receipt", "apk", "nonempty_output"])
def test_admission_fail_closed_before_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str,
) -> None:
    prep = _prepared(tmp_path, monkeypatch)
    candidate = CANDIDATE
    output = tmp_path / "execution"
    if mutation == "candidate":
        candidate = tmp_path / "wrong-candidate"
    elif mutation == "missing_predecessor":
        (prep / "stage-terminal.json").unlink()
    elif mutation == "terminal":
        path = prep / "stage-terminal.json"
        document = json.loads(path.read_bytes())
        document["status"] = "rejected"
        path.write_text(json.dumps(document))
    elif mutation == "raw_receipt":
        path = prep / "lanes" / "lane-01" / "preparation-receipt.json"
        assert path.is_file()
        path.chmod(0o644)
        path.write_bytes(path.read_bytes() + b" ")
    elif mutation == "apk":
        path = prep / "lanes" / "lane-01" / "artifacts" / "build" / "app-debug.apk"
        path.chmod(0o644)
        path.write_bytes(b"drifted")
    else:
        output.mkdir()
        (output / "existing").write_text("prior attempt")
    session = runtime_family_execution.RecordingRuntimeFamilySession()
    with pytest.raises(runtime_family_execution.RuntimeFamilyExecutionError):
        runtime_family_execution.execute_runtime_family(
            candidate_root=candidate, predecessor_root=prep, output_root=output,
            observations=_policies(), session=session,
        )
    assert not session.started
    assert not (output / "stage-start.json").exists()
    assert not (output / "lanes").exists()


@pytest.mark.parametrize("state", ["started", "stopped", "state", "last_device", "lifecycle"])
def test_admission_rejects_reused_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str,
) -> None:
    prep = _prepared(tmp_path, monkeypatch)
    session = runtime_family_execution.RecordingRuntimeFamilySession()
    setattr(session, state, {"foreign": True} if state == "state" else ["foreign"] if state == "lifecycle" else True)
    output = tmp_path / "execution"
    with pytest.raises(runtime_family_execution.RuntimeFamilyExecutionError, match="family_session_already_exists"):
        _execute(prep, output, session=session)
    assert not output.exists()


@pytest.mark.parametrize("fault,check", [
    ("source_health_fault", "source"), ("tool_health_fault", "tool"), ("log_health_fault", "log_collection"),
])
def test_lane_local_shared_health_fault_aborts_without_next_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str, check: str,
) -> None:
    prep = _prepared(tmp_path, monkeypatch)
    first = RecordingLaneObservation(device=RecordingDevicePolicy(boundary_layout_fault="missing_input"), **{fault: True})
    receipt = _execute(prep, tmp_path / "execution", observations=(first, *_policies()[1:]))
    assert not receipt.accepted
    assert receipt.document["rows"][0]["failure_scope"] == "lane_local"
    continuation = next(item["checks"] for item in receipt.document["health"] if item["boundary"] == "continuation")
    assert continuation[check]["closed"] is False
    if check in ("source", "tool"):
        assert continuation[check]["observed"] != continuation[check]["reference"]
        assert continuation[check]["stdout"]
    else:
        assert continuation[check].get("stdout", "") == "" or continuation[check].get("error")
    assert [row["status"] for row in receipt.document["rows"][1:]] == ["not_attempted_due_to_family_abort"] * 3
    assert not (receipt.output_root / "lanes" / "lane-02").exists()


def test_session_start_failure_does_not_fabricate_attempts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prep = _prepared(tmp_path, monkeypatch)
    session = runtime_family_execution.RecordingRuntimeFamilySession()

    def refuse(_package: str, _activity: str):
        raise RuntimeError("start refused")

    monkeypatch.setattr(session, "start", refuse)
    receipt = _execute(prep, tmp_path / "execution", session=session)
    assert not receipt.accepted
    assert all(row["status"] == "not_attempted_due_to_family_abort" for row in receipt.document["rows"])
    assert not (receipt.output_root / "lanes").exists()
    assert (receipt.output_root / "session-teardown.json").is_file()


def test_teardown_failure_retains_terminal_attempt_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prep = _prepared(tmp_path, monkeypatch)
    session = runtime_family_execution.RecordingRuntimeFamilySession()

    def refuse():
        raise RuntimeError("stop refused")

    monkeypatch.setattr(session, "stop", refuse)
    receipt = _execute(prep, tmp_path / "execution", session=session)
    assert not receipt.accepted
    assert receipt.document["teardown"]["status"] == "failed"
    assert [row["status"] for row in receipt.document["rows"]] == ["accountable_concluded"] * 4
    for row in receipt.document["rows"]:
        assert hashlib.sha256(Path(row["receipt_path"]).read_bytes()).hexdigest() == row["receipt_sha256"]
        assert hashlib.sha256(Path(row["record_path"]).read_bytes()).hexdigest() == row["record_sha256"]


def test_hard_interruption_leaves_unsealed_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prep = _prepared(tmp_path, monkeypatch)
    session = runtime_family_execution.RecordingRuntimeFamilySession()

    def interrupt(_request):
        raise KeyboardInterrupt

    monkeypatch.setattr(runtime_attempt, "execute_runtime_attempt", interrupt)
    output = tmp_path / "execution"
    with pytest.raises(KeyboardInterrupt):
        _execute(prep, output, session=session)
    _assert_no_terminal(output)
    assert session.stopped
    assert (output / "session-teardown.json").is_file()


@pytest.mark.parametrize("partial", ["in_progress", "malformed", "missing"])
def test_nonterminal_attempt_exception_is_abandoned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, partial: str) -> None:
    prep = _prepared(tmp_path, monkeypatch)

    def interrupt(request):
        request.output_root.mkdir(parents=True, exist_ok=True)
        if partial != "missing":
            (request.output_root / "execution-record.json").write_text(
                json.dumps({"lifecycle_state": "in_progress"}) if partial == "in_progress" else "{broken"
            )
        raise RuntimeError("attempt interrupted after record establishment")

    monkeypatch.setattr(runtime_attempt, "execute_runtime_attempt", interrupt)
    output = tmp_path / "execution"
    with pytest.raises(runtime_family_execution.RuntimeFamilyExecutionError, match="abandoned"):
        _execute(prep, output)
    _assert_no_terminal(output)
    assert (output / "lanes" / "lane-01" / "execution-record.json").is_file() == (partial != "missing")
    assert not (output / "lanes" / "lane-02").exists()
    assert (output / "session-teardown.json").is_file()


def test_verifier_failure_preserves_sealed_attempt_reference(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prep = _prepared(tmp_path, monkeypatch)

    def reject(root):
        raise RuntimeError("offline verifier unavailable")

    monkeypatch.setattr(runtime_attempt, "verify_runtime_attempt", reject)
    output = tmp_path / "execution"
    with pytest.raises(runtime_family_execution.RuntimeFamilyExecutionError, match="abandoned"):
        _execute(prep, output)
    _assert_no_terminal(output)
    assert (output / "session-teardown.json").is_file()
    abort = json.loads((output / "family-abort.json").read_bytes())
    row = abort["rows"][0]
    assert row["status"] in ("accountable_concluded", "non_accountable")
    assert row["verification_error"]
    assert hashlib.sha256(Path(row["receipt_path"]).read_bytes()).hexdigest() == row["receipt_sha256"]
    assert hashlib.sha256(Path(row["record_path"]).read_bytes()).hexdigest() == row["record_sha256"]
    assert not (output / "lanes" / "lane-02").exists()


def test_pre_record_refusal_does_not_invent_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prep = _prepared(tmp_path, monkeypatch)

    def refuse(request):
        raise ValueError("pre-record request refused")

    monkeypatch.setattr(runtime_attempt, "execute_runtime_attempt", refuse)
    receipt = _execute(prep, tmp_path / "execution")
    assert not receipt.accepted
    assert all(row["status"] == "not_attempted_due_to_family_abort" for row in receipt.document["rows"])
    assert not (receipt.output_root / "lanes").exists()


@pytest.mark.parametrize("filename", ["family-execution.json", "stage-terminal.json"])
def test_sealing_write_failure_leaves_no_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filename: str) -> None:
    prep = _prepared(tmp_path, monkeypatch)
    original = runtime_family_execution._write

    def refuse(path, document):
        if path.name == filename:
            raise OSError("recording disk write failure")
        return original(path, document)

    monkeypatch.setattr(runtime_family_execution, "_write", refuse)
    output = tmp_path / "execution"
    with pytest.raises(OSError):
        _execute(prep, output)
    assert not (output / "stage-terminal.json").exists()
    assert (output / "session-teardown.json").is_file()
    assert len(list(output.glob("lanes/*/execution-record.json"))) == 4


@pytest.mark.parametrize("fault", ["refused", "serial_changed", "fields_missing", "settings_missing", "identity_drifted"])
def test_identity_drift_aborts_later_lanes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str) -> None:
    prep = _prepared(tmp_path, monkeypatch)
    first = RecordingLaneObservation(device=RecordingDevicePolicy(session_drift_fault=fault))
    receipt = _execute(prep, tmp_path / "execution", observations=(first, *_policies()[1:]))
    assert not receipt.accepted
    assert [row["status"] for row in receipt.document["rows"][1:]] == ["not_attempted_due_to_family_abort"] * 3
    assert not (receipt.output_root / "lanes" / "lane-02").exists()


def test_shared_session_carries_state_but_not_operation_counts() -> None:
    session = runtime_family_execution.RecordingRuntimeFamilySession(serial="custom-recording")
    first = session.start("example.package", "example.Activity")
    first.probe_session()
    state = first.session_state()
    state.update(installed_digest="a" * 64, pid=123, launched=True, log=["recorded line"], epoch=42.0)
    session.state = state
    second = session.adapter(RecordingDevicePolicy(), "example.package", "example.Activity")
    assert second.session_state() == state
    assert second.serial == "custom-recording"
    assert not second.operation_counts()
    session.stop()


def test_family_probe_rejects_raw_output_contradiction(monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    device = runtime_attempt.RecordingRuntimeDevice()
    probe = device.probe_session()
    monkeypatch.setattr(device, "probe_session", lambda: replace(probe, outputs=("contradiction", *probe.outputs[1:])))
    result = runtime_family_execution._probe(device, probe.fields)
    assert not result["closed"]
    assert not result["checks"]["raw_outputs_match_fields"]
    assert result["probe"]["outputs"][0] == "contradiction"


@pytest.mark.parametrize("flag", ["--model", "--retry", "--replacement", "--expected-verdict", "--reduce-family", "--device-serial"])
def test_execute_cli_rejects_forbidden_flags(flag: str) -> None:
    with pytest.raises(SystemExit) as error:
        runtime_calibration.main([
            "execute-family", "--candidate-root", str(CANDIDATE),
            "--predecessor-root", str(MAPPING), "--output-root", "/tmp/unused-family-execution",
            "--recording-observations", "/tmp/unused-observations.json", flag, "forbidden",
        ])
    assert error.value.code == 2


def test_execute_family_never_calls_model_or_retries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prep = _prepared(tmp_path, monkeypatch)
    original = runtime_attempt.execute_runtime_attempt
    calls: list[str] = []

    def exactly_once(request):
        calls.append(request.lane_id)
        if len(calls) > 4:
            raise AssertionError("attempt retried or replaced")
        return original(request)

    monkeypatch.setattr(runtime_attempt, "execute_runtime_attempt", exactly_once)
    import subprocess
    from aiverify.runner.codex_backend import CodexCliBackend

    def forbidden(*args, **kwargs):
        pytest.fail("recording family crossed a live model/device/process boundary")

    monkeypatch.setattr(CodexCliBackend, "execute", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(runtime_attempt.AdbRuntimeDevice, "__init__", forbidden)
    receipt = _execute(prep, tmp_path / "execution")
    assert receipt.accepted
    assert calls == list(runtime_mapping.FROZEN_LANE_ORDER)
    assert receipt.document["invocations"] == {"model_calls": 0, "retries": 0, "replacements": 0}
    assert all("model" not in row and "retry" not in row and "replacement" not in row for row in receipt.document["rows"])


def test_successful_prepared_family_one_session_four_verified_attempts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prep = _prepared(tmp_path, monkeypatch)
    session = runtime_family_execution.RecordingRuntimeFamilySession()
    receipt = runtime_family_execution.execute_runtime_family(
        candidate_root=CANDIDATE, predecessor_root=prep, output_root=tmp_path / "execution",
        observations=_policies(), session=session,
    )
    document = receipt.to_dict()
    assert receipt.accepted, document["abort_reason"]
    assert [row["status"] for row in document["rows"]] == ["accountable_concluded"] * 4
    assert [entry["operation"] for entry in session.lifecycle] == ["recording_cold_start", "recording_cold_stop"]
    assert session.started and session.stopped
    assert document["invocations"] == {"model_calls": 0, "retries": 0, "replacements": 0}
    assert not any("expected_split_observed" in json.dumps(document) for _ in (0,))
    assert document["session"]["reference"]["closed"]
    assert len([entry for entry in document["health"] if entry["boundary"] == "after"]) == 4
    for index, row in enumerate(document["rows"], 1):
        root = receipt.output_root / "lanes" / f"lane-{index:02d}"
        verified = verify_runtime_attempt(root)
        assert verified["verified"] is True
        assert verified["receipt_sha256"] == row["receipt_sha256"]
        assert verified["recomputed"]["l1_outcome"] == "inconclusive"
        assert verified["recomputed"]["l2_outcome"] == ("pass" if index % 2 else "fail")
        assert (root / "execution-record.json").is_file()
    assert (receipt.output_root / "stage-terminal.json").is_file()
    for entry in document["artifact_inventory"]:
        path = receipt.output_root / entry["path"]
        assert path.is_file() and path.stat().st_size == entry["bytes"]


def test_accountable_surprise_does_not_select_lanes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prep = _prepared(tmp_path, monkeypatch)
    receipt = runtime_family_execution.execute_runtime_family(
        candidate_root=CANDIDATE, predecessor_root=prep, output_root=tmp_path / "execution",
        observations=_policies(save=(True, True, True, True)),
    )
    assert receipt.accepted
    assert len([row for row in receipt.document["rows"] if row["status"] == "accountable_concluded"]) == 4


def test_lane_local_continuation_rechecks_shared_health(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prep = _prepared(tmp_path, monkeypatch)
    policies = (RecordingLaneObservation(device=RecordingDevicePolicy(boundary_layout_fault="missing_input")), *_policies()[1:])
    receipt = runtime_family_execution.execute_runtime_family(
        candidate_root=CANDIDATE, predecessor_root=prep, output_root=tmp_path / "execution",
        observations=policies,
    )
    assert receipt.document["rows"][0]["status"] == "non_accountable"
    assert receipt.document["rows"][0]["failure_scope"] == "lane_local"
    checks = next(item["checks"] for item in receipt.document["health"] if item["boundary"] == "continuation")
    assert set(checks) == {"verifier", "input", "preparation_integrity", "device_session", "source", "tool", "log_collection"}
    assert all(entry["closed"] for entry in checks.values()), checks
    assert [row["status"] for row in receipt.document["rows"][1:]] == ["accountable_concluded"] * 3
    assert not receipt.accepted


@pytest.mark.parametrize("policy", [
    RecordingLaneObservation(device=RecordingDevicePolicy(log_dump_fault="empty_dump")),
    RecordingLaneObservation(device=RecordingDevicePolicy(session_drift_fault="identity_drifted")),
])
def test_shared_failure_aborts_without_fabricated_attempts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, policy: RecordingLaneObservation) -> None:
    prep = _prepared(tmp_path, monkeypatch)
    receipt = runtime_family_execution.execute_runtime_family(
        candidate_root=CANDIDATE, predecessor_root=prep, output_root=tmp_path / "execution",
        observations=(policy, *_policies()[1:]),
    )
    assert not receipt.accepted
    assert receipt.document["rows"][0]["status"] == "non_accountable"
    assert all(row["status"] == "not_attempted_due_to_family_abort" for row in receipt.document["rows"][1:])
    assert not list((receipt.output_root / "lanes" / "lane-02").glob("*"))
    assert (receipt.output_root / "session-teardown.json").is_file()


def test_admission_rejects_without_session_or_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prep = _prepared(tmp_path, monkeypatch)
    session = runtime_family_execution.RecordingRuntimeFamilySession()
    path = prep / "lanes" / "lane-01" / "artifacts" / "build" / "app-debug.apk"
    path.chmod(0o644)
    path.write_bytes(b"drifted")
    path.chmod(0o444)
    output = tmp_path / "execution"
    with pytest.raises(runtime_family_execution.RuntimeFamilyExecutionError):
        runtime_family_execution.execute_runtime_family(
            candidate_root=CANDIDATE, predecessor_root=prep, output_root=output,
            observations=_policies(), session=session,
        )
    assert not session.started
    assert not output.exists()


def test_cli_with_real_preparation_and_opaque_observations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    prep = _prepared(tmp_path, monkeypatch)
    config = tmp_path / "opaque-observations.json"
    config.write_text(json.dumps({
        "schema_version": 1, "evidence_class": "recorded_simulation",
        "lanes": [
            {"lane_id": lane_id, "observations": {"save_enabled": index % 2 == 0}}
            for index, lane_id in enumerate(runtime_mapping.FROZEN_LANE_ORDER)
        ],
    }))
    output = tmp_path / "execution"
    assert runtime_calibration.main([
        "execute-family", "--candidate-root", str(CANDIDATE),
        "--predecessor-root", str(prep), "--output-root", str(output),
        "--recording-observations", str(config),
    ]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "accepted"
    assert (output / "family-execution.json").is_file()
    assert [row["status"] for row in printed["rows"]] == ["accountable_concluded"] * 4


def test_cli_config_forbids_expected_verdict_and_lane_order(tmp_path: Path) -> None:
    path = tmp_path / "observations.json"
    rows = [{"lane_id": name, "observations": {}} for name in runtime_mapping.FROZEN_LANE_ORDER]
    for changed in (dict(rows[0], observations={"expected_verdict": "fail"}), rows[1]):
        altered = rows.copy()
        altered[0] = changed
        path.write_text(json.dumps({"schema_version": 1, "evidence_class": "recorded_simulation", "lanes": altered}))
        with pytest.raises(runtime_family_execution.RuntimeFamilyExecutionError):
            runtime_family_execution.load_recording_observations(path)
