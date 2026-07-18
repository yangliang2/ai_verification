from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from aiverify.runner.command import CommandResult, CommandRunner
from aiverify.runner.execution_identity import (
    ExecutionIdentityCollector,
    ExecutionIdentityError,
    verify_execution_provenance,
)
from aiverify.runner.run_spec import load_run_spec


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(args: list[str], *, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


class IdentityCommandRunner(CommandRunner):
    def __init__(
        self,
        *,
        host: Path,
        binaries: dict[str, Path],
        installed_hashes: dict[str, str],
    ) -> None:
        self.host = host
        self.binaries = binaries
        self.installed_hashes = installed_hashes
        self.calls: list[list[str]] = []

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        self.calls.append(list(args))
        binary_name = Path(args[0]).name
        if binary_name == "git":
            process = subprocess.run(
                args,
                cwd=cwd,
                text=True,
                capture_output=True,
                check=False,
            )
            return CommandResult(
                args=list(args),
                stdout=process.stdout,
                stderr=process.stderr,
                returncode=process.returncode,
            )
        if len(args) == 2 and args[1] in {"--version", "version"}:
            versions = {
                "android": "1.0.test\n",
                "adb": "Android Debug Bridge version 1.0.41\n",
                "codex": "codex-cli 0.144.5\n",
            }
            return CommandResult(args=list(args), stdout=versions[binary_name], stderr="", returncode=0)
        if binary_name == "android" and args[1] == "run":
            return CommandResult(
                args=list(args),
                stdout="Status: ok\nDeployed org.example.app\n",
                stderr="",
                returncode=0,
            )
        if binary_name == "adb":
            tail = args[3:]
            if tail == ["shell", "getprop", "ro.build.version.sdk"]:
                return CommandResult(args=list(args), stdout="35\n", stderr="", returncode=0)
            if tail == ["shell", "getprop", "ro.build.fingerprint"]:
                return CommandResult(args=list(args), stdout="google/test/fingerprint\n", stderr="", returncode=0)
            if tail == ["shell", "getprop", "ro.kernel.qemu"]:
                return CommandResult(args=list(args), stdout="1\n", stderr="", returncode=0)
            if tail == ["shell", "getprop", "ro.product.model"]:
                return CommandResult(args=list(args), stdout="sdk_gphone64_arm64\n", stderr="", returncode=0)
            if tail == ["shell", "getprop", "ro.product.device"]:
                return CommandResult(args=list(args), stdout="emu64a\n", stderr="", returncode=0)
            if tail == ["emu", "avd", "name"]:
                return CommandResult(args=list(args), stdout="aiverify_api35\nOK\n", stderr="", returncode=0)
            if tail == ["shell", "pm", "path", "org.example.app"]:
                return CommandResult(
                    args=list(args),
                    stdout=(
                        "package:/data/app/org.example.app/base.apk\n"
                        "package:/data/app/org.example.app/split_config.apk\n"
                    ),
                    stderr="",
                    returncode=0,
                )
            if tail[:2] == ["shell", "sha256sum"]:
                installed_path = tail[2]
                return CommandResult(
                    args=list(args),
                    stdout=f"{self.installed_hashes[installed_path]}  {installed_path}\n",
                    stderr="",
                    returncode=0,
                )
            if tail == [
                "shell",
                "cmd",
                "package",
                "resolve-activity",
                "--brief",
                "-n",
                "org.example.app/org.example.MainActivity",
            ]:
                return CommandResult(
                    args=list(args),
                    stdout="org.example.app/org.example.MainActivity\n",
                    stderr="",
                    returncode=0,
                )
        raise AssertionError(f"unexpected command: {args}")


def _write_role_receipt(path: Path, *, binary: Path, workdir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    observation = {
        "session_meta": {
            "id": "thread-1",
            "cwd": str(workdir),
            "cli_version": "0.144.5",
            "source": "exec",
        },
        "turn_context": {
            "turn_id": "turn-1",
            "model": "gpt-5.1-codex",
        },
    }
    observation_sha256 = hashlib.sha256(
        json.dumps(
            observation, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "role": "journey_driver",
                "backend": "codex_cli",
                "binary": {
                    "requested": str(binary),
                    "resolved_path": str(binary),
                    "sha256": _sha256(binary),
                    "version": "codex-cli 0.144.5",
                },
                "requested_model": "gpt-5.1-codex",
                "effective_model": "gpt-5.1-codex",
                "effective_model_source": {
                    "kind": "codex_session_turn_context",
                    "observation_sha256": observation_sha256,
                    "thread_id": "thread-1",
                    "turn_id": "turn-1",
                },
                "source_observation": observation,
                "command": {
                    "argv_without_prompt": [
                        str(binary),
                        "exec",
                        "--json",
                        "--output-schema",
                        "/schema.json",
                        "--cd",
                        str(workdir),
                        "--dangerously-bypass-approvals-and-sandbox",
                        "--model",
                        "gpt-5.1-codex",
                    ],
                    "prompt_sha256": "b" * 64,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_collector_binds_effective_execution_and_verifies_provenance(tmp_path: Path) -> None:
    host = tmp_path / "host"
    host.mkdir()
    _git(["init", "-q"], cwd=host)
    _git(["config", "user.name", "Test"], cwd=host)
    _git(["config", "user.email", "test@example.com"], cwd=host)
    (host / "source.txt").write_text("baseline\n", encoding="utf-8")
    (host / ".gitignore").write_text("apks/\n", encoding="utf-8")
    _git(["add", "source.txt", ".gitignore"], cwd=host)
    _git(["commit", "-qm", "baseline"], cwd=host)
    _git(["remote", "add", "origin", "https://example.invalid/upstream.git"], cwd=host)

    apk_dir = host / "apks"
    apk_dir.mkdir()
    base_apk = apk_dir / "base.apk"
    split_apk = apk_dir / "split_config.apk"
    base_apk.write_bytes(b"base apk")
    split_apk.write_bytes(b"split apk")
    run_spec_path = tmp_path / "run-spec.yaml"
    run_spec_path.write_text(
        "host_project: host\n"
        "apk_glob: apks/*.apk\n"
        "package: org.example.app\n"
        "activity: org.example.MainActivity\n"
        "scenario:\n"
        "  id: identity-smoke\n"
        "  user_actions:\n"
        "    - Inspect the current screen\n",
        encoding="utf-8",
    )
    spec = load_run_spec(run_spec_path)

    binaries: dict[str, Path] = {}
    for name in ("android", "adb", "codex"):
        path = tmp_path / "bin" / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(f"fake {name}\n".encode())
        path.chmod(0o755)
        binaries[name] = path
    git_bin = Path(shutil.which("git") or "git")
    installed_hashes = {
        "/data/app/org.example.app/base.apk": _sha256(base_apk),
        "/data/app/org.example.app/split_config.apk": _sha256(split_apk),
    }
    command_runner = IdentityCommandRunner(
        host=host,
        binaries=binaries,
        installed_hashes=installed_hashes,
    )
    run_dir = tmp_path / "run"
    artifact_dir = run_dir / "artifacts"
    collector = ExecutionIdentityCollector(
        run_dir=run_dir,
        artifact_dir=artifact_dir,
        attempt_id="attempt-1",
        spec=spec,
        run_spec_path=run_spec_path,
        workdir=host,
        device="emulator-5554",
        requested_driver_model="gpt-5.1-codex",
        requested_l3_model=None,
        command_runner=command_runner,
        android_bin=str(binaries["android"]),
        adb_bin=str(binaries["adb"]),
        codex_bin=str(binaries["codex"]),
        git_bin=str(git_bin),
    )

    collector.capture_static()
    collector.deploy()

    (host / "source.txt").write_text("runtime drift\n", encoding="utf-8")
    with pytest.raises(ExecutionIdentityError, match="host identity drifted"):
        collector.finalize(
            l1={"outcome": "inconclusive"},
            l2={"outcome": "pass"},
            l3=None,
            l3_configured=False,
        )
    (host / "source.txt").write_text("baseline\n", encoding="utf-8")

    _write_role_receipt(
        artifact_dir / "identity-smoke-segment-0" / "codex-invocation-identity.json",
        binary=binaries["codex"],
        workdir=host,
    )
    binding = collector.finalize(
        l1={"outcome": "inconclusive"},
        l2={"outcome": "pass"},
        l3=None,
        l3_configured=False,
    )

    provenance = verify_execution_provenance(
        binding,
        attempt_id="attempt-1",
        scenario="identity-smoke",
        base_dir=run_dir,
    )
    assert provenance["run_spec"]["consumed_sha256"] == _sha256(run_spec_path)
    assert provenance["run_spec"]["snapshot_sha256"] == _sha256(
        run_dir / provenance["run_spec"]["snapshot_path"]
    )
    assert provenance["host"]["origin"] == "https://example.invalid/upstream.git"
    assert provenance["host"]["commit"] == _git(["rev-parse", "HEAD"], cwd=host)
    assert provenance["host"]["worktree"]["clean"] is True
    assert {item["sha256"] for item in provenance["apk"]["artifacts"]} == {
        _sha256(base_apk),
        _sha256(split_apk),
    }
    assert provenance["deployment"]["process"]["returncode"] == 0
    assert {
        item["sha256"] for item in provenance["deployment"]["installed_artifacts"]
    } == {_sha256(base_apk), _sha256(split_apk)}
    assert provenance["device"] == {
        "serial": "emulator-5554",
        "api_level": "35",
        "build_fingerprint": "google/test/fingerprint",
        "profile": {
            "kind": "emulator",
            "name": "aiverify_api35",
            "model": "sdk_gphone64_arm64",
            "device": "emu64a",
        },
        "identity_sha256": provenance["device"]["identity_sha256"],
    }
    assert provenance["roles"]["journey_driver"]["status"] == "invoked"
    assert provenance["roles"]["l3_semantic_judge"] == {
        "status": "not_applicable",
        "reason": "scenario_has_no_l3_spec",
        "requested_model": None,
        "invocations": [],
        "invocation_ledger": [],
    }

    def rejected(name: str, tampered: dict, message: str) -> None:
        tampered_path = run_dir / f"tampered-{name}.json"
        tampered_path.write_text(json.dumps(tampered) + "\n", encoding="utf-8")
        with pytest.raises(ExecutionIdentityError, match=message):
            verify_execution_provenance(
                {"path": tampered_path.name, "sha256": _sha256(tampered_path)},
                attempt_id="attempt-1",
                scenario="identity-smoke",
                base_dir=run_dir,
            )

    tampered = deepcopy(provenance)
    tampered["host"]["origin"] = "https://evil.invalid/replaced.git"
    rejected("host-origin", tampered, "host identity checksum mismatch")

    tampered = deepcopy(provenance)
    tampered["run_spec"]["package"] = "org.example.other"
    rejected("run-spec-package", tampered, "Run Spec snapshot contradicts")

    tampered = deepcopy(provenance)
    tampered["deployment"]["process"]["args"][2] = "--device=other-device"
    rejected("deployment-command", tampered, "deployment process checksum mismatch")

    tampered = deepcopy(provenance)
    tampered["host"]["worktree"]["status"] = " M source.txt\n"
    rejected("host-status", tampered, "host status checksum mismatch")

    tampered = deepcopy(provenance)
    del tampered["tools"]["adb"]
    rejected("missing-tool", tampered, "tool identity is incomplete")

    tampered = deepcopy(provenance)
    tampered["tools"]["android_cli"]["sha256"] = "e" * 64
    rejected("changed-tool", tampered, "tool identity checksum mismatch")

    tampered = deepcopy(provenance)
    tampered["run_spec"]["consumed_sha256"] = "c" * 64
    rejected("run-spec-drift", tampered, "consumed and snapshot checksums differ")

    tampered = deepcopy(provenance)
    tampered["apk"]["artifacts"].append(
        deepcopy(tampered["apk"]["artifacts"][0])
    )
    rejected("duplicate-apk", tampered, "APK identity path is duplicated")

    tampered = deepcopy(provenance)
    tampered["deployment"]["installed_artifacts"][0]["sha256"] = "d" * 64
    rejected("deployment-mismatch", tampered, "installed artifact set contradicts")

    tampered = deepcopy(provenance)
    tampered["roles"]["journey_driver"]["invocations"].append(
        deepcopy(tampered["roles"]["journey_driver"]["invocations"][0])
    )
    rejected("duplicate-role", tampered, "role thread or turn identity is duplicated")

    tampered = deepcopy(provenance)
    role_ref = tampered["roles"]["journey_driver"]["invocations"][0]
    role_receipt = json.loads(
        (run_dir / role_ref["path"]).read_text(encoding="utf-8")
    )
    role_receipt["effective_model"] = "gpt-5.2-codex"
    changed_role_path = run_dir / "tampered-role-receipt.json"
    changed_role_path.write_text(json.dumps(role_receipt) + "\n", encoding="utf-8")
    role_ref.update({"path": changed_role_path.name, "sha256": _sha256(changed_role_path)})
    rejected("changed-model", tampered, "requested and effective models differ")

    tampered = deepcopy(provenance)
    role_ref = tampered["roles"]["journey_driver"]["invocations"][0]
    role_receipt = json.loads(
        (run_dir / role_ref["path"]).read_text(encoding="utf-8")
    )
    role_receipt["source_observation"]["session_meta"]["cwd"] = str(tmp_path)
    role_receipt["effective_model_source"]["observation_sha256"] = hashlib.sha256(
        json.dumps(
            role_receipt["source_observation"],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    changed_role_path = run_dir / "tampered-role-cwd.json"
    changed_role_path.write_text(json.dumps(role_receipt) + "\n", encoding="utf-8")
    role_ref.update({"path": changed_role_path.name, "sha256": _sha256(changed_role_path)})
    rejected("changed-role-cwd", tampered, "role session cwd contradicts")

    with pytest.raises(ExecutionIdentityError, match="escapes the audit base"):
        verify_execution_provenance(
            {"path": "../execution-provenance.json", "sha256": "a" * 64},
            attempt_id="attempt-1",
            scenario="identity-smoke",
            base_dir=run_dir,
        )
