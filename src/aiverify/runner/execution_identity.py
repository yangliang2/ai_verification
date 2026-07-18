"""Effective execution identity capture and evidence-derived verification."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

from aiverify.runner.command import CommandResult, CommandRunner, SubprocessCommandRunner
from aiverify.runner.execution_record import write_bytes_artifact, write_json_artifact
from aiverify.runner.run_spec import RunSpec, RunSpecError, parse_run_spec


class ExecutionIdentityError(RuntimeError):
    """Raised when required execution identity is missing or contradictory."""


class ExecutionIdentityCollector:
    """Capture one attempt's static, deployment, device, tool, and role identity."""

    def __init__(
        self,
        *,
        run_dir: Path,
        artifact_dir: Path,
        attempt_id: str,
        spec: RunSpec,
        run_spec_path: Path,
        workdir: Path,
        device: str,
        requested_driver_model: str | None,
        requested_l3_model: str | None,
        command_runner: CommandRunner | None = None,
        android_bin: str = "android",
        adb_bin: str = "adb",
        codex_bin: str = "codex",
        git_bin: str = "git",
    ) -> None:
        self.run_dir = Path(run_dir).resolve()
        self.artifact_dir = Path(artifact_dir).resolve()
        self.attempt_id = attempt_id
        self.spec = spec
        self.run_spec_path = Path(run_spec_path).resolve()
        self.workdir = Path(workdir).resolve()
        self.device_serial = device
        self.requested_driver_model = requested_driver_model
        self.requested_l3_model = requested_l3_model
        self.runner = command_runner or SubprocessCommandRunner()
        self.android_bin = android_bin
        self.adb_bin = adb_bin
        self.codex_bin = codex_bin
        self.git_bin = git_bin
        self.identity_dir = self.run_dir / "identity"
        self.provenance_path = self.run_dir / "execution-provenance.json"
        self._static: dict | None = None
        self._deployment: dict | None = None

    def capture_static(self) -> None:
        """Capture immutable inputs before deployment or agent invocation."""
        source_bytes = self._run_spec_bytes()
        snapshot_path = self.identity_dir / "run-spec.yaml"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        write_bytes_artifact(snapshot_path, source_bytes)

        host = self._host_identity()
        patch_path = self.identity_dir / "host.patch"
        write_bytes_artifact(patch_path, host.pop("patch_bytes"))
        host["worktree"]["patch_path"] = self._evidence_path(patch_path)
        host["worktree"]["patch_sha256"] = _sha256_file(patch_path)

        apk_artifacts = self._apk_artifacts()
        device = self._device_identity()
        tools = self._tools_identity()
        host["identity_sha256"] = _identity_sha256(host)
        apk = {"artifacts": apk_artifacts}
        apk["identity_sha256"] = _identity_sha256(apk)
        device["identity_sha256"] = _identity_sha256(device)
        run_spec = {
            "invocation_path": str(self.run_spec_path),
            "consumed_sha256": _sha256_bytes(source_bytes),
            "snapshot_path": self._evidence_path(snapshot_path),
            "snapshot_sha256": _sha256_file(snapshot_path),
            "scenario": self.spec.scenario.id,
            "host_project": str(self.spec.host_project.resolve()),
            "apk_glob": self.spec.apk_glob,
            "package": self.spec.package,
            "activity": self.spec.activity,
        }
        if self.spec.host_locator is not None:
            locator = self.spec.host_locator
            run_spec["host_locator"] = {
                "root": locator.root,
                "resolution": locator.resolution,
                "resolved_path": str(locator.resolved_path),
                "expected_origin": locator.expected_origin,
                "expected_commit": locator.expected_commit,
            }
        run_spec["identity_sha256"] = _identity_sha256(run_spec)
        self._static = {
            "run_spec": run_spec,
            "host": host,
            "apk": apk,
            "device": device,
            "tools": tools,
        }

    def _tools_identity(self) -> dict:
        tools = {
            "android_cli": self._tool_identity(
                self.android_bin, [self.android_bin, "--version"]
            ),
            "adb": self._tool_identity(
                self.adb_bin, [self.adb_bin, "version"]
            ),
            "codex_cli": self._tool_identity(
                self.codex_bin, [self.codex_bin, "--version"]
            ),
            "git": self._tool_identity(
                self.git_bin, [self.git_bin, "--version"]
            ),
            "python": {
                "requested": sys.executable,
                "resolved_path": str(Path(sys.executable).resolve()),
                "sha256": _sha256_file(Path(sys.executable).resolve()),
                "version": platform.python_version(),
            },
        }
        for identity in tools.values():
            identity["identity_sha256"] = _identity_sha256(identity)
        return tools

    def deploy(self) -> dict:
        """Deploy the captured APK set and bind device-side installed bytes."""
        if self._static is None:
            raise ExecutionIdentityError("static identity must be captured before deploy")
        apk_artifacts = self._static["apk"]["artifacts"]
        command = [
            self.android_bin,
            "run",
            f"--device={self.device_serial}",
            "--apks=" + ",".join(item["path"] for item in apk_artifacts),
        ]
        if self.spec.activity:
            command.extend([f"--activity={self.spec.activity}", "--type=ACTIVITY"])
        process = self.runner.run(command, cwd=self.workdir, timeout_seconds=300)
        process_identity = _process_identity(process)
        if process.returncode != 0:
            self._deployment = {
                "target": self._target_identity(),
                "process": process_identity,
                "installed_artifacts": [],
            }
            raise ExecutionIdentityError(
                f"Android CLI deployment failed with exit code {process.returncode}"
            )

        installed_paths_result = self._adb("shell", "pm", "path", self.spec.package)
        installed_paths = [
            line.removeprefix("package:").strip()
            for line in installed_paths_result.stdout.splitlines()
            if line.startswith("package:") and line.removeprefix("package:").strip()
        ]
        if not installed_paths or len(installed_paths) != len(set(installed_paths)):
            raise ExecutionIdentityError("installed APK path set is empty or duplicated")
        installed_artifacts = []
        for installed_path in installed_paths:
            digest_result = self._adb("shell", "sha256sum", installed_path)
            digest = digest_result.stdout.strip().split()[0] if digest_result.stdout.strip() else ""
            if not _is_sha256(digest):
                raise ExecutionIdentityError(
                    f"device-side APK hash is missing for {installed_path}"
                )
            installed_artifacts.append({"path": installed_path, "sha256": digest})

        local_hashes = Counter(item["sha256"] for item in apk_artifacts)
        remote_hashes = Counter(item["sha256"] for item in installed_artifacts)
        if local_hashes != remote_hashes:
            raise ExecutionIdentityError(
                "deployed APK hashes contradict the captured local artifact set"
            )
        expected_component = _component(self.spec.package, self.spec.activity)
        if expected_component is None:
            raise ExecutionIdentityError("Run Spec launch component is required")
        component_result = self._adb(
            "shell",
            "cmd",
            "package",
            "resolve-activity",
            "--brief",
            "-n",
            expected_component,
        )
        resolved_component = _last_nonempty_line(component_result.stdout)
        if _component_value(resolved_component) != expected_component:
            raise ExecutionIdentityError(
                "resolved launch component contradicts the Run Spec"
            )
        device_after = self._device_identity()
        device_after["identity_sha256"] = _identity_sha256(device_after)
        if device_after != self._static["device"]:
            raise ExecutionIdentityError("device identity drifted during deployment")
        self._deployment = {
            "target": self._target_identity(),
            "process": process_identity,
            "installed_artifacts": installed_artifacts,
            "resolved_component": resolved_component,
            "device": device_after,
            "tools": {
                "android_cli_sha256": self._static["tools"]["android_cli"]["sha256"],
                "adb_sha256": self._static["tools"]["adb"]["sha256"],
            },
        }
        self._deployment["identity_sha256"] = _identity_sha256(self._deployment)
        return self._deployment

    def finalize(
        self,
        *,
        l1: dict,
        l2: dict,
        l3: dict | None,
        l3_configured: bool,
    ) -> dict[str, str]:
        """Write and verify the checksum-bound provenance manifest."""
        if self._static is None or self._deployment is None:
            raise ExecutionIdentityError("static and deployment identity are required")
        self._verify_no_drift()
        driver_paths = sorted(
            self.artifact_dir.glob("*/codex-invocation-identity.json")
        )
        l3_paths = sorted(
            (self.artifact_dir / "l3-judge").glob("l3-judge-call-*.identity.json")
        )
        l3_ledger_paths = sorted(
            (self.artifact_dir / "l3-judge").glob("l3-judge-call-*.invocation.json")
        )
        if not driver_paths:
            raise ExecutionIdentityError("journey driver identity receipt is missing")
        driver = self._role_identity(
            "journey_driver", driver_paths, self.requested_driver_model,
            ledger_paths=[],
        )
        if l3_paths:
            l3_role = self._role_identity(
                "l3_semantic_judge", l3_paths, self.requested_l3_model,
                ledger_paths=l3_ledger_paths,
            )
        elif not l3_configured:
            l3_role = _not_applicable_role(
                "scenario_has_no_l3_spec", self.requested_l3_model
            )
        elif l3 is None and any(
            verdict.get("outcome") == "fail" for verdict in (l1, l2)
        ):
            l3_role = _not_applicable_role(
                "gated_by_lower_oracle", self.requested_l3_model
            )
        else:
            raise ExecutionIdentityError("L3 judge identity receipt is missing")

        payload = {
            "schema_version": 1,
            "attempt_id": self.attempt_id,
            "scenario": self.spec.scenario.id,
            "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **self._static,
            "deployment": self._deployment,
            "roles": {
                "journey_driver": driver,
                "l3_semantic_judge": l3_role,
            },
        }
        write_json_artifact(self.provenance_path, payload)
        binding = {
            "path": self._evidence_path(self.provenance_path),
            "sha256": _sha256_file(self.provenance_path),
        }
        verify_execution_provenance(
            binding,
            attempt_id=self.attempt_id,
            scenario=self.spec.scenario.id,
            base_dir=self.run_dir,
        )
        return binding

    def verify_ready_for_agent(self) -> None:
        """Fail closed if captured inputs drift before agent invocation."""
        if self._static is None or self._deployment is None:
            raise ExecutionIdentityError("static and deployment identity are required")
        self._verify_no_drift()

    def _verify_no_drift(self) -> None:
        if _sha256_bytes(self._run_spec_bytes()) != self._static["run_spec"][
            "consumed_sha256"
        ]:
            raise ExecutionIdentityError("Run Spec identity drifted during execution")

        current_host = self._host_identity()
        patch_bytes = current_host.pop("patch_bytes")
        current_host["worktree"]["patch_path"] = self._static["host"]["worktree"][
            "patch_path"
        ]
        current_host["worktree"]["patch_sha256"] = _sha256_bytes(patch_bytes)
        current_host["identity_sha256"] = _identity_sha256(current_host)
        if current_host != self._static["host"]:
            raise ExecutionIdentityError("host identity drifted during execution")

        current_apk = {"artifacts": self._apk_artifacts()}
        current_apk["identity_sha256"] = _identity_sha256(current_apk)
        if current_apk != self._static["apk"]:
            raise ExecutionIdentityError("APK identity drifted during execution")

        current_device = self._device_identity()
        current_device["identity_sha256"] = _identity_sha256(current_device)
        if current_device != self._static["device"]:
            raise ExecutionIdentityError("device identity drifted during execution")

        current_tools = self._tools_identity()
        if current_tools != self._static["tools"]:
            raise ExecutionIdentityError("tool identity drifted during execution")

        installed = self._installed_artifacts()
        if installed != self._deployment["installed_artifacts"]:
            raise ExecutionIdentityError(
                "installed APK identity drifted during execution"
            )
        expected_component = self._deployment["target"]["component"]
        component_result = self._adb(
            "shell", "cmd", "package", "resolve-activity", "--brief", "-n",
            expected_component,
        )
        if _component_value(_last_nonempty_line(component_result.stdout)) != expected_component:
            raise ExecutionIdentityError(
                "launch component identity drifted during execution"
            )

    def _installed_artifacts(self) -> list[dict[str, str]]:
        installed_paths_result = self._adb("shell", "pm", "path", self.spec.package)
        installed_paths = [
            line.removeprefix("package:").strip()
            for line in installed_paths_result.stdout.splitlines()
            if line.startswith("package:") and line.removeprefix("package:").strip()
        ]
        if not installed_paths or len(installed_paths) != len(set(installed_paths)):
            raise ExecutionIdentityError("installed APK path set is empty or duplicated")
        installed_artifacts = []
        for installed_path in installed_paths:
            digest_result = self._adb("shell", "sha256sum", installed_path)
            digest = digest_result.stdout.strip().split()[0] if digest_result.stdout.strip() else ""
            if not _is_sha256(digest):
                raise ExecutionIdentityError(
                    f"device-side APK hash is missing for {installed_path}"
                )
            installed_artifacts.append({"path": installed_path, "sha256": digest})
        return installed_artifacts

    def _run_spec_bytes(self) -> bytes:
        if self.spec.source_path is None or self.spec.source_sha256 is None:
            raise ExecutionIdentityError("Run Spec source identity is unavailable")
        if self.spec.source_path.resolve() != self.run_spec_path:
            raise ExecutionIdentityError("Run Spec invocation path contradicts loaded source")
        try:
            source_bytes = self.run_spec_path.read_bytes()
        except OSError as error:
            raise ExecutionIdentityError(f"Run Spec source cannot be read: {error}") from error
        if _sha256_bytes(source_bytes) != self.spec.source_sha256:
            raise ExecutionIdentityError("Run Spec drifted after it was consumed")
        if self.spec.host_project.resolve() != self.workdir:
            raise ExecutionIdentityError("runner workdir contradicts Run Spec host_project")
        return source_bytes

    def _host_identity(self) -> dict:
        root = Path(
            self._git("rev-parse", "--show-toplevel").stdout.strip()
        ).resolve()
        if root != self.workdir:
            raise ExecutionIdentityError("workdir is not the captured git repository root")
        origin = self._git("remote", "get-url", "origin").stdout.strip()
        commit = self._git("rev-parse", "HEAD").stdout.strip()
        status = self._git("status", "--porcelain=v1", "--untracked-files=all").stdout
        patch = self._git("diff", "--binary", "HEAD").stdout.encode("utf-8")
        untracked_output = self._git(
            "ls-files", "--others", "--exclude-standard"
        ).stdout
        untracked = []
        for relative in sorted(line for line in untracked_output.splitlines() if line):
            path = root / relative
            if not path.is_file():
                raise ExecutionIdentityError(
                    f"unsupported non-file untracked host input: {relative}"
                )
            untracked.append(
                {"path": relative, "sha256": _sha256_file(path)}
            )
        if not origin or not _is_sha1(commit):
            raise ExecutionIdentityError("git origin or commit identity is unavailable")
        if self.spec.host_locator is not None and (
            origin != self.spec.host_locator.expected_origin
        ):
            raise ExecutionIdentityError(
                "host origin contradicts portable Run Spec locator"
            )
        if self.spec.host_locator is not None and (
            commit != self.spec.host_locator.expected_commit
        ):
            raise ExecutionIdentityError(
                "host commit contradicts portable Run Spec locator"
            )
        return {
            "repository_root": str(root),
            "origin": origin,
            "commit": commit,
            "worktree": {
                "clean": not bool(status.strip()),
                "status": status,
                "status_sha256": _sha256_bytes(status.encode("utf-8")),
                "untracked_files": untracked,
            },
            "patch_bytes": patch,
        }

    def _apk_artifacts(self) -> list[dict[str, object]]:
        override = os.environ.get("AIVERIFY_DEPLOYED_APK")
        if override:
            path = Path(override).resolve()
            if not path.is_file():
                raise ExecutionIdentityError(f"deployed APK override is missing: {path}")
            return [{
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }]
        paths = sorted(
            path.resolve()
            for path in self.spec.host_project.glob(self.spec.apk_glob)
            if path.is_file()
        )
        if not paths or len(paths) != len(set(paths)):
            raise ExecutionIdentityError("APK artifact set is empty or duplicated")
        return [
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
            for path in paths
        ]

    def _device_identity(self) -> dict:
        api_level = self._adb("shell", "getprop", "ro.build.version.sdk").stdout.strip()
        fingerprint = self._adb(
            "shell", "getprop", "ro.build.fingerprint"
        ).stdout.strip()
        qemu = self._adb("shell", "getprop", "ro.kernel.qemu").stdout.strip()
        model = self._adb("shell", "getprop", "ro.product.model").stdout.strip()
        product_device = self._adb(
            "shell", "getprop", "ro.product.device"
        ).stdout.strip()
        if not api_level.isdigit() or not fingerprint or not model or not product_device:
            raise ExecutionIdentityError("required device identity is unavailable")
        if qemu == "1":
            avd_result = self._adb("emu", "avd", "name")
            profile_name = next(
                (
                    line.strip()
                    for line in avd_result.stdout.splitlines()
                    if line.strip() and line.strip() != "OK"
                ),
                "",
            )
            if not profile_name:
                raise ExecutionIdentityError("emulator AVD identity is unavailable")
            kind = "emulator"
        elif qemu in {"0", ""}:
            profile_name = model
            kind = "physical_device"
        else:
            raise ExecutionIdentityError("unsupported ro.kernel.qemu identity")
        return {
            "serial": self.device_serial,
            "api_level": api_level,
            "build_fingerprint": fingerprint,
            "profile": {
                "kind": kind,
                "name": profile_name,
                "model": model,
                "device": product_device,
            },
        }

    def _tool_identity(self, requested: str, version_args: list[str]) -> dict:
        path = _resolve_binary(requested)
        result = self.runner.run(version_args, timeout_seconds=30)
        version = (result.stdout or result.stderr).strip()
        if result.returncode != 0 or not version:
            raise ExecutionIdentityError(f"tool version is unavailable: {requested}")
        return {
            "requested": requested,
            "resolved_path": str(path),
            "sha256": _sha256_file(path),
            "version": version,
        }

    def _role_identity(
        self,
        role: str,
        paths: list[Path],
        requested_model: str | None,
        ledger_paths: list[Path],
    ) -> dict:
        refs = []
        receipts = []
        for path in paths:
            receipt = _load_json(path, label=f"{role} identity receipt")
            _validate_role_receipt(
                receipt,
                expected_role=role,
                requested_model=requested_model,
                expected_binary=self._static["tools"]["codex_cli"],
                expected_workdir=self.workdir,
            )
            receipts.append(receipt)
            refs.append({"path": self._evidence_path(path), "sha256": _sha256_file(path)})
        ledger_refs = []
        for expected_index, path in enumerate(ledger_paths, start=1):
            ledger = _load_json(path, label=f"{role} invocation ledger")
            if ledger != {
                "schema_version": 1,
                "role": role,
                "call_index": expected_index,
                "requested_model": requested_model,
                "argv_without_prompt": ledger.get("argv_without_prompt"),
                "prompt_sha256": ledger.get("prompt_sha256"),
            } or not isinstance(ledger["argv_without_prompt"], list) or not _is_sha256(
                ledger["prompt_sha256"]
            ):
                raise ExecutionIdentityError("L3 invocation ledger is invalid")
            receipt_command = receipts[expected_index - 1]["command"]
            if (
                ledger["argv_without_prompt"] != receipt_command["argv_without_prompt"]
                or ledger["prompt_sha256"] != receipt_command["prompt_sha256"]
            ):
                raise ExecutionIdentityError(
                    "L3 invocation ledger contradicts identity receipt"
                )
            ledger_refs.append(
                {"path": self._evidence_path(path), "sha256": _sha256_file(path)}
            )
        if role == "l3_semantic_judge" and len(ledger_refs) != len(refs):
            raise ExecutionIdentityError(
                "L3 invoked call is missing a terminal identity receipt"
            )
        return {
            "status": "invoked",
            "requested_model": requested_model,
            "invocations": refs,
            "invocation_ledger": ledger_refs,
        }

    def _git(self, *args: str) -> CommandResult:
        result = self.runner.run([self.git_bin, *args], cwd=self.workdir, timeout_seconds=30)
        if result.returncode != 0:
            raise ExecutionIdentityError(
                f"git identity command failed: {' '.join(args)}: {result.stderr.strip()}"
            )
        return result

    def _adb(self, *args: str) -> CommandResult:
        result = self.runner.run(
            [self.adb_bin, "-s", self.device_serial, *args],
            timeout_seconds=30,
        )
        if result.returncode != 0:
            raise ExecutionIdentityError(
                f"adb identity command failed: {' '.join(args)}: {result.stderr.strip()}"
            )
        return result

    def _target_identity(self) -> dict:
        component = _component(self.spec.package, self.spec.activity)
        if component is None:
            raise ExecutionIdentityError("Run Spec launch component is required")
        return {
            "device": self.device_serial,
            "package": self.spec.package,
            "component": component,
        }

    def _evidence_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.run_dir))
        except ValueError as error:
            raise ExecutionIdentityError(
                f"attempt evidence is outside the run directory: {path}"
            ) from error


def verify_execution_provenance(
    binding: object,
    *,
    attempt_id: str,
    scenario: str,
    base_dir: Path | None = None,
) -> dict:
    """Load checksum-bound provenance and reject missing or contradictory identity."""
    if not isinstance(binding, dict):
        raise ExecutionIdentityError("execution provenance binding must be an object")
    path_value = binding.get("path")
    expected_sha = binding.get("sha256")
    if not isinstance(path_value, str) or not _is_sha256(expected_sha):
        raise ExecutionIdentityError("execution provenance binding is incomplete")
    evidence_root = Path(base_dir).resolve() if base_dir is not None else None
    path = _resolve_evidence_path(path_value, evidence_root=evidence_root)
    if not path.is_file() or _sha256_file(path) != expected_sha:
        raise ExecutionIdentityError("execution provenance checksum mismatch")
    payload = _load_json(path, label="execution provenance")
    if payload.get("schema_version") != 1:
        raise ExecutionIdentityError("unsupported execution provenance schema")
    if payload.get("attempt_id") != attempt_id or payload.get("scenario") != scenario:
        raise ExecutionIdentityError("execution provenance attempt or scenario mismatch")
    _validate_run_spec_identity(
        payload.get("run_spec"), scenario=scenario, evidence_root=evidence_root
    )
    _validate_host_identity(payload.get("host"), evidence_root=evidence_root)
    if payload["host"]["repository_root"] != payload["run_spec"]["host_project"]:
        raise ExecutionIdentityError("host root contradicts the consumed Run Spec")
    locator = payload["run_spec"].get("host_locator")
    if locator is not None and (
        payload["host"]["origin"] != locator["expected_origin"]
        or payload["host"]["commit"] != locator["expected_commit"]
    ):
        raise ExecutionIdentityError(
            "host repository identity contradicts the consumed Run Spec locator"
        )
    local_hashes = _validate_apk_identity(payload.get("apk"))
    host_root = Path(payload["host"]["repository_root"])
    for artifact in payload["apk"]["artifacts"]:
        try:
            Path(artifact["path"]).relative_to(host_root)
        except ValueError as error:
            raise ExecutionIdentityError("APK path is outside the captured host") from error
    _validate_device_identity(payload.get("device"))
    _validate_tools(payload.get("tools"))
    _validate_deployment(
        payload.get("deployment"),
        local_hashes=local_hashes,
        local_artifacts=payload["apk"]["artifacts"],
        run_spec=payload["run_spec"],
        device=payload["device"],
        tools=payload["tools"],
    )
    roles = payload.get("roles")
    if not isinstance(roles, dict) or set(roles) != {
        "journey_driver",
        "l3_semantic_judge",
    }:
        raise ExecutionIdentityError("role identity set is incomplete or duplicated")
    driver_identities = _verify_role(
        roles["journey_driver"],
        expected_role="journey_driver",
        expected_binary=payload["tools"]["codex_cli"],
        evidence_root=evidence_root,
        expected_workdir=Path(payload["host"]["repository_root"]),
    )
    l3_identities = _verify_role(
        roles["l3_semantic_judge"],
        expected_role="l3_semantic_judge",
        expected_binary=payload["tools"]["codex_cli"],
        evidence_root=evidence_root,
        expected_workdir=Path(payload["host"]["repository_root"]),
    )
    all_identities = driver_identities | l3_identities
    if len(all_identities) != len(driver_identities) + len(l3_identities):
        raise ExecutionIdentityError("role thread or turn identity is duplicated")
    return payload


def _validate_run_spec_identity(
    value: object, *, scenario: str, evidence_root: Path | None
) -> None:
    if not isinstance(value, dict):
        raise ExecutionIdentityError("Run Spec identity is missing")
    for key in ("invocation_path", "snapshot_path", "host_project", "apk_glob", "package"):
        if not isinstance(value.get(key), str) or not value[key]:
            raise ExecutionIdentityError(f"Run Spec identity field is missing: {key}")
    if value.get("scenario") != scenario:
        raise ExecutionIdentityError("Run Spec scenario contradicts provenance")
    for key in ("consumed_sha256", "snapshot_sha256"):
        if not _is_sha256(value.get(key)):
            raise ExecutionIdentityError(f"Run Spec checksum is invalid: {key}")
    snapshot = _resolve_evidence_path(
        value["snapshot_path"], evidence_root=evidence_root
    )
    if not snapshot.is_file() or _sha256_file(snapshot) != value["snapshot_sha256"]:
        raise ExecutionIdentityError("Run Spec snapshot checksum mismatch")
    if value["consumed_sha256"] != value["snapshot_sha256"]:
        raise ExecutionIdentityError("Run Spec consumed and snapshot checksums differ")
    invocation_path = Path(value["invocation_path"])
    if not invocation_path.is_absolute():
        raise ExecutionIdentityError("Run Spec invocation path is not absolute")
    locator = value.get("host_locator")
    if locator is not None:
        if (
            not isinstance(locator, dict)
            or set(locator)
            != {
                "root",
                "resolution",
                "resolved_path",
                "expected_origin",
                "expected_commit",
            }
            or not isinstance(locator.get("root"), str)
            or locator.get("resolution") not in {"environment", "override"}
            or locator.get("resolved_path") != value["host_project"]
            or not isinstance(locator.get("expected_origin"), str)
            or not locator["expected_origin"]
            or not _is_sha1(locator.get("expected_commit"))
        ):
            raise ExecutionIdentityError("portable host locator identity is invalid")
    try:
        snapshot_data = yaml.safe_load(snapshot.read_text(encoding="utf-8"))
        snapshot_spec = parse_run_spec(
            snapshot_data,
            base_dir=invocation_path.parent,
            environ={},
            host_project_override=(
                Path(value["host_project"]) if locator is not None else None
            ),
        )
    except (OSError, UnicodeDecodeError, yaml.YAMLError, RunSpecError) as error:
        raise ExecutionIdentityError(
            f"Run Spec snapshot cannot be parsed: {error}"
        ) from error
    expected = {
        "scenario": snapshot_spec.scenario.id,
        "host_project": str(snapshot_spec.host_project.resolve()),
        "apk_glob": snapshot_spec.apk_glob,
        "package": snapshot_spec.package,
        "activity": snapshot_spec.activity,
    }
    if any(value.get(key) != expected_value for key, expected_value in expected.items()):
        raise ExecutionIdentityError("Run Spec snapshot contradicts captured identity")
    if locator is not None and locator != {
        "root": snapshot_spec.host_locator.root,
        "resolution": locator["resolution"],
        "resolved_path": str(snapshot_spec.host_locator.resolved_path),
        "expected_origin": snapshot_spec.host_locator.expected_origin,
        "expected_commit": snapshot_spec.host_locator.expected_commit,
    }:
        raise ExecutionIdentityError(
            "Run Spec snapshot contradicts portable host locator identity"
        )
    if value.get("identity_sha256") != _identity_sha256(value):
        raise ExecutionIdentityError("Run Spec identity checksum mismatch")


def _validate_host_identity(value: object, *, evidence_root: Path | None) -> None:
    if not isinstance(value, dict):
        raise ExecutionIdentityError("host identity is missing")
    root = value.get("repository_root")
    if not isinstance(root, str) or not Path(root).is_absolute():
        raise ExecutionIdentityError("host repository root is invalid")
    if not isinstance(value.get("origin"), str) or not value["origin"]:
        raise ExecutionIdentityError("host origin is missing")
    if not _is_sha1(value.get("commit")):
        raise ExecutionIdentityError("host commit is invalid")
    worktree = value.get("worktree")
    if not isinstance(worktree, dict) or not isinstance(worktree.get("clean"), bool):
        raise ExecutionIdentityError("host worktree identity is missing")
    for key in ("status_sha256", "patch_sha256"):
        if not _is_sha256(worktree.get(key)):
            raise ExecutionIdentityError(f"host worktree checksum is invalid: {key}")
    status = worktree.get("status")
    if not isinstance(status, str) or _sha256_bytes(status.encode("utf-8")) != worktree["status_sha256"]:
        raise ExecutionIdentityError("host status checksum mismatch")
    if worktree["clean"] != (not bool(status.strip())):
        raise ExecutionIdentityError("host clean flag contradicts captured status")
    patch_path = worktree.get("patch_path")
    if not isinstance(patch_path, str) or _sha256_file(
        _resolve_evidence_path(patch_path, evidence_root=evidence_root)
    ) != worktree["patch_sha256"]:
        raise ExecutionIdentityError("host patch checksum mismatch")
    untracked = worktree.get("untracked_files")
    if not isinstance(untracked, list):
        raise ExecutionIdentityError("host untracked identity is missing")
    paths = [item.get("path") for item in untracked if isinstance(item, dict)]
    if len(paths) != len(untracked) or len(paths) != len(set(paths)):
        raise ExecutionIdentityError("host untracked identity is invalid or duplicated")
    if any(not _is_sha256(item.get("sha256")) for item in untracked):
        raise ExecutionIdentityError("host untracked checksum is invalid")
    if value.get("identity_sha256") != _identity_sha256(value):
        raise ExecutionIdentityError("host identity checksum mismatch")


def _validate_apk_identity(value: object) -> Counter[str]:
    artifacts = value.get("artifacts") if isinstance(value, dict) else None
    if not isinstance(artifacts, list) or not artifacts:
        raise ExecutionIdentityError("APK identity set is missing")
    paths = []
    hashes = []
    for item in artifacts:
        if not isinstance(item, dict):
            raise ExecutionIdentityError("APK identity entry is invalid")
        path = item.get("path")
        size = item.get("bytes")
        digest = item.get("sha256")
        if not isinstance(path, str) or not isinstance(size, int) or size < 0 or not _is_sha256(digest):
            raise ExecutionIdentityError("APK identity entry is incomplete")
        paths.append(path)
        hashes.append(digest)
    if len(paths) != len(set(paths)):
        raise ExecutionIdentityError("APK identity path is duplicated")
    if value.get("identity_sha256") != _identity_sha256(value):
        raise ExecutionIdentityError("APK identity checksum mismatch")
    return Counter(hashes)


def _validate_deployment(
    value: object,
    *,
    local_hashes: Counter[str],
    local_artifacts: list[dict],
    run_spec: dict,
    device: dict,
    tools: dict,
) -> None:
    if not isinstance(value, dict):
        raise ExecutionIdentityError("deployment identity is missing")
    process = value.get("process")
    if not isinstance(process, dict) or process.get("returncode") != 0:
        raise ExecutionIdentityError("deployment process did not succeed")
    if process.get("identity_sha256") != _identity_sha256(process):
        raise ExecutionIdentityError("deployment process checksum mismatch")
    if not isinstance(process.get("stdout"), str) or not isinstance(process.get("stderr"), str):
        raise ExecutionIdentityError("deployment process output is incomplete")
    target = value.get("target")
    expected_component = _component(run_spec["package"], run_spec.get("activity"))
    if target != {
        "device": device["serial"],
        "package": run_spec["package"],
        "component": expected_component,
    }:
        raise ExecutionIdentityError("deployment target contradicts Run Spec or device")
    expected_args = [
        tools["android_cli"]["requested"],
        "run",
        f"--device={device['serial']}",
        "--apks=" + ",".join(item["path"] for item in local_artifacts),
    ]
    if run_spec.get("activity"):
        expected_args.extend(
            [f"--activity={run_spec['activity']}", "--type=ACTIVITY"]
        )
    if process.get("args") != expected_args:
        raise ExecutionIdentityError("deployment command contradicts captured identity")
    installed = value.get("installed_artifacts")
    if not isinstance(installed, list) or not installed:
        raise ExecutionIdentityError("installed artifact identity is missing")
    paths = []
    hashes = []
    for item in installed:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not _is_sha256(item.get("sha256")):
            raise ExecutionIdentityError("installed artifact identity is invalid")
        paths.append(item["path"])
        hashes.append(item["sha256"])
    if len(paths) != len(set(paths)) or Counter(hashes) != local_hashes:
        raise ExecutionIdentityError("installed artifact set contradicts local APKs")
    if value.get("device") != device:
        raise ExecutionIdentityError("deployment device identity contradicts capture")
    tool_binding = value.get("tools")
    if tool_binding != {
        "android_cli_sha256": tools["android_cli"]["sha256"],
        "adb_sha256": tools["adb"]["sha256"],
    }:
        raise ExecutionIdentityError("deployment tool identity contradicts capture")
    if _component_value(value.get("resolved_component")) != expected_component:
        raise ExecutionIdentityError("deployment component cross-check failed")
    if value.get("identity_sha256") != _identity_sha256(value):
        raise ExecutionIdentityError("deployment identity checksum mismatch")


def _validate_device_identity(value: object) -> None:
    if not isinstance(value, dict):
        raise ExecutionIdentityError("device identity is missing")
    if value.get("identity_sha256") != _identity_sha256(value):
        raise ExecutionIdentityError("device identity checksum mismatch")
    if not isinstance(value.get("serial"), str) or not value["serial"]:
        raise ExecutionIdentityError("device serial is missing")
    if not isinstance(value.get("api_level"), str) or not value["api_level"].isdigit():
        raise ExecutionIdentityError("device API level is invalid")
    if not isinstance(value.get("build_fingerprint"), str) or not value["build_fingerprint"]:
        raise ExecutionIdentityError("device fingerprint is missing")
    profile = value.get("profile")
    if not isinstance(profile, dict) or profile.get("kind") not in {"emulator", "physical_device"}:
        raise ExecutionIdentityError("declared device profile is invalid")
    if any(not isinstance(profile.get(key), str) or not profile[key] for key in ("name", "model", "device")):
        raise ExecutionIdentityError("declared device profile is incomplete")


def _validate_tools(value: object) -> None:
    required = {"android_cli", "adb", "codex_cli", "git", "python"}
    if not isinstance(value, dict) or set(value) != required:
        raise ExecutionIdentityError("execution-critical tool identity is incomplete")
    for name, identity in value.items():
        if not isinstance(identity, dict):
            raise ExecutionIdentityError(f"tool identity is invalid: {name}")
        if not isinstance(identity.get("resolved_path"), str) or not identity["resolved_path"]:
            raise ExecutionIdentityError(f"tool path is missing: {name}")
        if not _is_sha256(identity.get("sha256")):
            raise ExecutionIdentityError(f"tool binary checksum is invalid: {name}")
        if not isinstance(identity.get("version"), str) or not identity["version"]:
            raise ExecutionIdentityError(f"tool version is missing: {name}")
        if identity.get("identity_sha256") != _identity_sha256(identity):
            raise ExecutionIdentityError(f"tool identity checksum mismatch: {name}")


def _verify_role(
    value: object,
    *,
    expected_role: str,
    expected_binary: dict,
    evidence_root: Path | None,
    expected_workdir: Path,
) -> set[tuple[str, str]]:
    if not isinstance(value, dict):
        raise ExecutionIdentityError(f"role identity is missing: {expected_role}")
    status = value.get("status")
    requested_model = value.get("requested_model")
    invocations = value.get("invocations")
    if requested_model is not None and (
        not isinstance(requested_model, str) or not requested_model
    ):
        raise ExecutionIdentityError(f"role requested model is invalid: {expected_role}")
    if status == "not_applicable":
        if expected_role != "l3_semantic_judge" or value.get("reason") not in {
            "scenario_has_no_l3_spec",
            "gated_by_lower_oracle",
        } or invocations != [] or value.get("invocation_ledger") != []:
            raise ExecutionIdentityError("not-applicable role identity is invalid")
        return set()
    if status != "invoked" or not isinstance(invocations, list) or not invocations:
        raise ExecutionIdentityError(f"invoked role identity is incomplete: {expected_role}")
    paths = []
    identities: set[tuple[str, str]] = set()
    for ref in invocations:
        if not isinstance(ref, dict) or not isinstance(ref.get("path"), str) or not _is_sha256(ref.get("sha256")):
            raise ExecutionIdentityError("role receipt reference is invalid")
        path = _resolve_evidence_path(
            ref["path"], evidence_root=evidence_root
        )
        if not path.is_file() or _sha256_file(path) != ref["sha256"]:
            raise ExecutionIdentityError("role receipt checksum mismatch")
        receipt = _load_json(path, label=f"{expected_role} receipt")
        _validate_role_receipt(
            receipt,
            expected_role=expected_role,
            requested_model=requested_model,
            expected_binary=expected_binary,
            expected_workdir=expected_workdir,
        )
        source = receipt["effective_model_source"]
        identity = (source["thread_id"], source["turn_id"])
        if identity in identities:
            raise ExecutionIdentityError("role thread or turn identity is duplicated")
        identities.add(identity)
        paths.append(str(path.resolve()))
    if len(paths) != len(set(paths)):
        raise ExecutionIdentityError("role receipt reference is duplicated")
    ledger = value.get("invocation_ledger")
    if expected_role == "journey_driver":
        if ledger != []:
            raise ExecutionIdentityError("journey driver invocation ledger is invalid")
    else:
        _verify_l3_ledger(
            ledger,
            invocations=invocations,
            requested_model=requested_model,
            evidence_root=evidence_root,
        )
    return identities


def _validate_role_receipt(
    receipt: object,
    *,
    expected_role: str,
    requested_model: str | None,
    expected_binary: dict | None = None,
    expected_workdir: Path | None = None,
) -> None:
    if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
        raise ExecutionIdentityError("role identity receipt schema is invalid")
    if receipt.get("role") != expected_role or receipt.get("backend") != "codex_cli":
        raise ExecutionIdentityError("role or backend identity contradicts invocation")
    if receipt.get("requested_model") != requested_model:
        raise ExecutionIdentityError("role requested model contradicts runner input")
    effective_model = receipt.get("effective_model")
    if not isinstance(effective_model, str) or not effective_model:
        raise ExecutionIdentityError("role effective model is missing")
    if requested_model is not None and effective_model != requested_model:
        raise ExecutionIdentityError("role requested and effective models differ")
    binary = receipt.get("binary")
    if not isinstance(binary, dict) or not _is_sha256(binary.get("sha256")) or not isinstance(binary.get("version"), str) or not binary["version"]:
        raise ExecutionIdentityError("role backend binary identity is incomplete")
    if expected_binary is not None and any(
        binary.get(key) != expected_binary.get(key)
        for key in ("resolved_path", "sha256", "version")
    ):
        raise ExecutionIdentityError("role backend binary contradicts tool identity")
    source = receipt.get("effective_model_source")
    observation = receipt.get("source_observation")
    if not isinstance(source, dict) or source.get("kind") != "codex_session_turn_context" or not _is_sha256(source.get("observation_sha256")):
        raise ExecutionIdentityError("role effective-model source is invalid")
    if not isinstance(observation, dict):
        raise ExecutionIdentityError("role source observation is missing")
    meta = observation.get("session_meta")
    turn = observation.get("turn_context")
    if not isinstance(meta, dict) or not isinstance(turn, dict):
        raise ExecutionIdentityError("role source observation is incomplete")
    if source["observation_sha256"] != _identity_sha256(observation):
        raise ExecutionIdentityError("role source observation checksum mismatch")
    if meta.get("id") != source.get("thread_id") or turn.get("turn_id") != source.get("turn_id") or turn.get("model") != effective_model:
        raise ExecutionIdentityError("role source observation contradicts receipt")
    if meta.get("source") != "exec":
        raise ExecutionIdentityError("role source is not a Codex exec invocation")
    if _version_number(str(meta.get("cli_version", ""))) != _version_number(
        binary["version"]
    ):
        raise ExecutionIdentityError("role session CLI version contradicts binary")
    if expected_workdir is not None:
        try:
            session_cwd = Path(str(meta.get("cwd", ""))).resolve()
        except OSError as error:
            raise ExecutionIdentityError("role session cwd is invalid") from error
        if session_cwd != expected_workdir.resolve():
            raise ExecutionIdentityError("role session cwd contradicts captured host")
    command = receipt.get("command")
    argv = command.get("argv_without_prompt") if isinstance(command, dict) else None
    if not isinstance(argv, list) or not all(isinstance(arg, str) for arg in argv):
        raise ExecutionIdentityError("role command identity is invalid")
    if not _is_sha256(command.get("prompt_sha256")):
        raise ExecutionIdentityError("role prompt checksum is invalid")
    if len(argv) < 2 or argv[0] != binary.get("requested") or argv[1] != "exec":
        raise ExecutionIdentityError("role command backend contradicts receipt")
    if argv.count("--cd") != 1 or argv.count("--json") != 1:
        raise ExecutionIdentityError("role command context is incomplete")
    try:
        command_cwd = Path(argv[argv.index("--cd") + 1]).resolve()
    except (ValueError, IndexError, OSError) as error:
        raise ExecutionIdentityError("role command cwd is invalid") from error
    if expected_workdir is not None and command_cwd != expected_workdir.resolve():
        raise ExecutionIdentityError("role command cwd contradicts captured host")
    if expected_role == "journey_driver":
        if "--output-schema" not in argv or "--dangerously-bypass-approvals-and-sandbox" not in argv:
            raise ExecutionIdentityError("journey driver command shape is invalid")
    else:
        try:
            sandbox = argv[argv.index("--sandbox") + 1]
        except (ValueError, IndexError) as error:
            raise ExecutionIdentityError("L3 judge command sandbox is invalid") from error
        if sandbox != "read-only":
            raise ExecutionIdentityError("L3 judge command sandbox is invalid")
    if requested_model is not None:
        try:
            command_model = argv[argv.index("--model") + 1]
        except (ValueError, IndexError) as error:
            raise ExecutionIdentityError("role model override is absent from command") from error
        if command_model != requested_model:
            raise ExecutionIdentityError("role command model contradicts runner input")


def _verify_l3_ledger(
    value: object,
    *,
    invocations: list[dict],
    requested_model: str | None,
    evidence_root: Path | None,
) -> None:
    if not isinstance(value, list) or len(value) != len(invocations):
        raise ExecutionIdentityError("L3 invocation ledger is incomplete")
    for expected_index, ref in enumerate(value, start=1):
        if not isinstance(ref, dict) or not isinstance(ref.get("path"), str) or not _is_sha256(ref.get("sha256")):
            raise ExecutionIdentityError("L3 invocation ledger reference is invalid")
        path = _resolve_evidence_path(ref["path"], evidence_root=evidence_root)
        if not path.is_file() or _sha256_file(path) != ref["sha256"]:
            raise ExecutionIdentityError("L3 invocation ledger checksum mismatch")
        ledger = _load_json(path, label="L3 invocation ledger")
        if (
            ledger.get("schema_version") != 1
            or ledger.get("role") != "l3_semantic_judge"
            or ledger.get("call_index") != expected_index
            or ledger.get("requested_model") != requested_model
            or not isinstance(ledger.get("argv_without_prompt"), list)
            or not _is_sha256(ledger.get("prompt_sha256"))
        ):
            raise ExecutionIdentityError("L3 invocation ledger is invalid")
        receipt_ref = invocations[expected_index - 1]
        receipt_path = _resolve_evidence_path(
            receipt_ref["path"], evidence_root=evidence_root
        )
        receipt = _load_json(receipt_path, label="L3 identity receipt")
        command = receipt.get("command")
        if not isinstance(command, dict) or (
            ledger["argv_without_prompt"] != command.get("argv_without_prompt")
            or ledger["prompt_sha256"] != command.get("prompt_sha256")
        ):
            raise ExecutionIdentityError(
                "L3 invocation ledger contradicts identity receipt"
            )


def _not_applicable_role(reason: str, requested_model: str | None) -> dict:
    return {
        "status": "not_applicable",
        "reason": reason,
        "requested_model": requested_model,
        "invocations": [],
        "invocation_ledger": [],
    }


def _process_identity(result: CommandResult) -> dict:
    identity = {
        "args": list(result.args),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    identity["identity_sha256"] = _identity_sha256(identity)
    return identity


def _resolve_binary(binary: str) -> Path:
    resolved = shutil.which(binary)
    if resolved is None and Path(binary).expanduser().is_file():
        resolved = str(Path(binary).expanduser())
    if resolved is None:
        raise ExecutionIdentityError(f"tool binary cannot be resolved: {binary}")
    path = Path(resolved).resolve()
    if not path.is_file():
        raise ExecutionIdentityError(f"tool binary is not a file: {path}")
    return path


def _resolve_evidence_path(path_value: str, *, evidence_root: Path | None) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        if evidence_root is not None:
            try:
                path.resolve().relative_to(evidence_root)
            except ValueError as error:
                raise ExecutionIdentityError(
                    "execution evidence path escapes the audit base directory"
                ) from error
        return path
    if evidence_root is None:
        raise ExecutionIdentityError(
            "relative execution evidence path requires an audit base directory"
        )
    resolved = (evidence_root / path).resolve()
    try:
        resolved.relative_to(evidence_root)
    except ValueError as error:
        raise ExecutionIdentityError(
            "execution evidence path escapes the audit base directory"
        ) from error
    return resolved


def _component(package: str, activity: str | None) -> str | None:
    if not activity:
        return None
    if "/" in activity:
        return _component_value(activity)
    if activity.startswith("."):
        return f"{package}/{package}{activity}"
    return f"{package}/{activity}"


def _component_value(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if "/." in value:
        package, activity = value.split("/", 1)
        return f"{package}/{package}{activity}"
    return value


def _last_nonempty_line(value: str) -> str:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _load_json(path: Path, *, label: str) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ExecutionIdentityError(f"invalid {label}: {error}") from error
    if not isinstance(value, dict):
        raise ExecutionIdentityError(f"{label} must be an object")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise ExecutionIdentityError(f"cannot hash {path}: {error}") from error
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _identity_sha256(value: dict) -> str:
    payload = {key: item for key, item in value.items() if key != "identity_sha256"}
    return _sha256_bytes(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )


def _version_number(value: str) -> str:
    return value.strip().split()[-1] if value.strip() else ""


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _is_sha1(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(
        character in "0123456789abcdef" for character in value
    )
