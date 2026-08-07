from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiverify.harness.device import AdbResult
from aiverify.harness.device.adb import FakeAdbRunner
from aiverify.harness.device.controller import DeviceController
from aiverify.bench.m9_formal import (
    LANE_IDS,
    M9FormalExecutionError,
    _clear_package,
    _oracle_conclusion,
    _reconcile,
)


def test_formal_oracle_conclusion_is_terminal_and_fail_closed() -> None:
    accountable = {"status": "completed", "accounting_eligible": True}
    assert _oracle_conclusion({"execution": accountable, "l1": {"outcome": "fail"}}) == "locally_supported"
    assert _oracle_conclusion({"execution": accountable, "l1": {"outcome": "pass"}, "l3": {"outcome": "pass"}}) == "locally_rejected"
    assert _oracle_conclusion({"execution": accountable, "l1": {"outcome": "pass"}, "l3": {"outcome": "invalid"}}) == "inconclusive"
    assert _oracle_conclusion({"execution": {"status": "non_accountable", "accounting_eligible": False}}) == "inconclusive"


def test_formal_reconciliation_requires_all_six_accountable_rows(tmp_path: Path) -> None:
    rows = [
        {
            "lane_id": lane_id,
            "role": "defect" if index < 3 else "control",
            "accountable": True,
            "finding_conclusion": "supported" if index < 3 else "rejected",
            "falsification_review": {
                "status": "complete",
                "outcome": "survived",
            },
        }
        for index, lane_id in enumerate(LANE_IDS)
    ]
    result = _reconcile(tmp_path, rows, {"status": "pass"})
    assert result["aggregate_result"] == "Supported"
    assert result["counts"] == {
        "lane_count": 6,
        "accountable": 6,
        "defect_supported": 3,
        "control_locally_rejected": 3,
        "falsification_review_survived": 6,
        "contradiction_packet_pre_side_effect": True,
    }
    assert result["retry_count"] == 0
    assert result["replacement_count"] == 0
    persisted = json.loads((tmp_path / "final-reconciliation.json").read_text(encoding="utf-8"))
    assert all("role" not in lane for lane in persisted["lanes"])

    rows[4] = {**rows[4], "accountable": False}
    rejected = _reconcile(tmp_path / "rejected", rows, {"status": "pass"})
    assert rejected["aggregate_result"] == "Not Supported"
    assert rejected["supported_gate"]["six_of_six_accountable"] is False


def test_formal_package_clear_proves_uninstalled_package_is_clean(tmp_path: Path) -> None:
    runner = FakeAdbRunner()
    runner.enqueue(AdbResult(stdout="", stderr="", returncode=1))
    controller = DeviceController(serial="emulator-r1", runner=runner)
    lane_dir = tmp_path / "lane"
    lane_dir.mkdir()
    _clear_package(
        lane_dir,
        device_serial="emulator-r1",
        package="com.example.r1",
        controller=controller,
    )
    receipt = (lane_dir / "package-clear.json").read_text(encoding="utf-8")
    assert '"status": "already_absent"' in receipt
    assert '"device_serial": "emulator-r1"' in receipt
    assert '"package": "com.example.r1"' in receipt


def test_formal_package_clear_persists_an_installed_clear_failure(
    tmp_path: Path,
) -> None:
    runner = FakeAdbRunner()
    runner.enqueue_many(
        [
            AdbResult(
                stdout="package:/data/app/com.example.r1/base.apk\n",
                stderr="",
                returncode=0,
            ),
            AdbResult(stdout="Failed\n", stderr="", returncode=1),
        ]
    )
    controller = DeviceController(serial="emulator-r1", runner=runner)
    lane_dir = tmp_path / "lane"
    lane_dir.mkdir()

    with pytest.raises(
        M9FormalExecutionError,
        match="installed package data clear failed",
    ):
        _clear_package(
            lane_dir,
            device_serial="emulator-r1",
            package="com.example.r1",
            controller=controller,
        )

    receipt = json.loads(
        (lane_dir / "package-clear.json").read_text(encoding="utf-8")
    )
    assert receipt["status"] == "clear_failed"
    assert receipt["clear_performed"] is True
