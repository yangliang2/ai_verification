"""Run Spec loading, validation, and dry-run planning."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

import yaml


SUPPORTED_SYSTEM_EVENTS = frozenset(
    {
        "rotate",
        "kill_background",
        "revoke_permission",
        "network_off",
        "network_on",
        "wait",
        "low_memory",
        "app_to_background",
        "app_to_foreground",
        "locale_change",
        "battery_low",
        "dark_mode",
        "process_death",
    }
)

SUPPORTED_SEED_KINDS = frozenset(
    {"unspecified", "injected_defect", "baseline_control"}
)
SUPPORTED_ORACLE_LEVELS = frozenset({"L1", "L2", "L3"})
SUPPORTED_ORACLE_DEFECT_CLASSES = frozenset(
    {
        "crash_stability",
        "state_loss",
        "ui_rendering",
        "performance_regression",
        "permission_security",
    }
)


class RunSpecError(ValueError):
    """Raised when a Run Spec is missing required fields or has invalid values."""


@dataclass(frozen=True)
class AssertionSpec:
    """State assertion evaluated against evidence checkpoints."""

    resource_id: str
    attr: str
    expected: str


@dataclass(frozen=True)
class SystemEventSpec:
    """System event injected at a Journey Segment Boundary."""

    step_index: int
    event: str
    args: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MetricContextSpec:
    """Benchmark metric metadata kept separate from oracle verdict output."""

    seed_kind: str = "unspecified"
    taxonomy_category: str | None = None
    taxonomy_pattern_id: str | None = None
    expected_oracle_level: str | None = None
    expected_oracle_defect_class: str | None = None


@dataclass(frozen=True)
class AppSmokeSpec:
    """Optional host-specific app surface validation for live preflight."""

    package: str | None = None
    activity: str | None = None
    target_resource_id: str | None = None
    target_text: str | None = None
    target_content_desc: str | None = None
    app_settle_seconds: float = 3.0


@dataclass(frozen=True)
class LiveValidationSpec:
    """Runner-enforced live-validation preflight configuration."""

    android_bin: str = "android"
    adb_bin: str = "adb"
    timeout_seconds: int = 30
    snippet_chars: int = 4000
    app_smoke: AppSmokeSpec | None = None


@dataclass(frozen=True)
class ScenarioSpec:
    """Scenario portion of a Run Spec."""

    id: str
    user_actions: list[str] = field(default_factory=list)
    system_events: list[SystemEventSpec] = field(default_factory=list)
    assertions: list[AssertionSpec] = field(default_factory=list)
    # Zero-based Journey Segment Boundary order, normalized by system-event step_index.
    l2_boundary_index: int | None = None
    expected_behavior: str = ""
    metric_context: MetricContextSpec = field(default_factory=MetricContextSpec)
    # L3 语义判定用的"正确行为规格"。与 expected_behavior 不同：expected_behavior
    # 描述本次运行（含注入缺陷时）的预期观测，会泄露缺陷位置，不能喂给 judge；
    # l3_spec 只描述产品的正确行为，matched pair 的 baseline/defect 共用同一份。
    # 非空时 runner 才会在 L1/L2 均未 fail 的前提下调用 L3。
    l3_spec: str = ""


@dataclass(frozen=True)
class DryRunPlan:
    """Actions a runner would take for a valid Run Spec."""

    run_id: str
    artifact_dir: Path
    actions: list[str]


@dataclass(frozen=True)
class HostProjectLocator:
    """Portable declaration and one execution's resolved host binding."""

    root: str
    resolution: str
    resolved_path: Path
    expected_origin: str
    expected_commit: str


@dataclass(frozen=True)
class RunSpec:
    """Single-file input contract for one reproducible verification run."""

    host_project: Path
    apk_glob: str
    package: str
    activity: str | None
    diff: Path | None
    spec: Path | None
    scenario: ScenarioSpec
    host_locator: HostProjectLocator | None = None
    live_validation: LiveValidationSpec = field(default_factory=LiveValidationSpec)
    source_path: Path | None = None
    source_sha256: str | None = None

    def dry_run_plan(self, artifact_root: Path) -> DryRunPlan:
        """Return a dry-run action plan without touching host projects or devices."""
        run_id = self.scenario.id
        artifact_dir = Path(artifact_root) / run_id
        actions = [
            f"validate run spec {run_id}",
            f"prepare artifacts at {artifact_dir}",
            f"apply diff {self.diff}" if self.diff else "skip diff application",
            f"build host project {self.host_project}",
            f"locate APKs with glob {self.apk_glob}",
            f"deploy package {self.package}",
            "run live-validation preflight",
            "execute Journey segments",
            f"evaluate {len(self.scenario.assertions)} assertion(s)",
            "write verdict JSON",
        ]
        return DryRunPlan(run_id=run_id, artifact_dir=artifact_dir, actions=actions)


def load_run_spec(
    path: str | Path,
    *,
    environ: Mapping[str, str] | None = None,
    host_project_override: str | Path | None = None,
) -> RunSpec:
    """Load and validate a Run Spec YAML file."""
    src = Path(path).resolve()
    try:
        source_bytes = src.read_bytes()
        data = yaml.safe_load(source_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise RunSpecError(f"Run Spec 读取失败：{exc}") from exc
    except yaml.YAMLError as exc:
        raise RunSpecError(f"Run Spec YAML 解析失败：{exc}") from exc
    return replace(
        parse_run_spec(
            data,
            base_dir=src.parent,
            environ=environ,
            host_project_override=host_project_override,
        ),
        source_path=src,
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
    )


def parse_run_spec(
    data: object,
    *,
    base_dir: Path | None = None,
    environ: Mapping[str, str] | None = None,
    host_project_override: str | Path | None = None,
) -> RunSpec:
    """Parse and validate a Run Spec mapping."""
    if base_dir is None:
        base_dir = Path.cwd()
    if not isinstance(data, dict):
        raise RunSpecError("Run Spec 顶层必须是映射")

    host_project, host_locator = _parse_host_project(
        data.get("host_project"),
        base_dir=base_dir,
        environ=os.environ if environ is None else environ,
        override=host_project_override,
    )
    apk_glob = _required_str(data, "apk_glob")
    package = _required_str(data, "package")
    activity = _optional_str(data, "activity")
    diff = _optional_path(data, "diff", base_dir=base_dir)
    spec = _optional_path(data, "spec", base_dir=base_dir)
    live_validation = _parse_live_validation(data.get("live_validation"))
    _validate_live_validation_context(
        live_validation,
        package=package,
        activity=activity,
    )

    raw_scenario = data.get("scenario")
    if not isinstance(raw_scenario, dict):
        raise RunSpecError("Run Spec 缺少 scenario 映射")
    scenario = _parse_scenario(raw_scenario)

    return RunSpec(
        host_project=_resolve_path(host_project, base_dir=base_dir),
        apk_glob=apk_glob,
        package=package,
        activity=activity,
        diff=diff,
        spec=spec,
        scenario=scenario,
        host_locator=host_locator,
        live_validation=live_validation,
    )


_HOST_ENV_LOCATOR = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")


def _parse_host_project(
    raw: object,
    *,
    base_dir: Path,
    environ: Mapping[str, str],
    override: str | Path | None,
) -> tuple[Path, HostProjectLocator | None]:
    if isinstance(raw, str) and raw.strip():
        if override is not None:
            raise RunSpecError(
                "host_project override requires a structured portable locator"
            )
        return _resolve_path(raw, base_dir=base_dir), None
    if not isinstance(raw, dict):
        raise RunSpecError("字段 host_project 必须是路径字符串或 portable locator")

    root = _required_str(raw, "root")
    origin = _required_str(raw, "origin")
    commit = _required_str(raw, "commit")
    match = _HOST_ENV_LOCATOR.fullmatch(root)
    if match is None:
        raise RunSpecError(
            "portable host_project.root 必须是 ${UPPER_CASE_VARIABLE}"
        )
    if re.fullmatch(r"[0-9a-fA-F]{40}", commit) is None:
        raise RunSpecError("portable host_project.commit 必须是 40 位 Git commit")

    variable = match.group(1)
    if override is not None:
        override_path = Path(override).expanduser()
        if not override_path.is_absolute():
            raise RunSpecError(
                "portable host_project override must be an absolute path"
            )
        resolved = override_path.resolve()
        declared_environment = environ.get(variable)
        if declared_environment:
            environment_path = Path(declared_environment).expanduser()
            if not environment_path.is_absolute():
                raise RunSpecError(
                    f"portable host locator must resolve to an absolute path: {variable}"
                )
            if environment_path.resolve() != resolved:
                raise RunSpecError(
                    f"portable host_project override contradicts environment: {variable}"
                )
        resolution = "override"
    else:
        value = environ.get(variable)
        if not value:
            raise RunSpecError(f"portable host locator environment is missing: {variable}")
        resolved = Path(value).expanduser()
        if not resolved.is_absolute():
            raise RunSpecError(
                f"portable host locator must resolve to an absolute path: {variable}"
            )
        resolved = resolved.resolve()
        resolution = "environment"
    return resolved, HostProjectLocator(
        root=root,
        resolution=resolution,
        resolved_path=resolved,
        expected_origin=origin,
        expected_commit=commit.lower(),
    )


def _parse_live_validation(raw: object) -> LiveValidationSpec:
    if raw is None:
        return LiveValidationSpec()
    if not isinstance(raw, dict):
        raise RunSpecError("live_validation 必须是映射")

    return LiveValidationSpec(
        android_bin=_optional_nonempty_str(raw, "android_bin") or "android",
        adb_bin=_optional_nonempty_str(raw, "adb_bin") or "adb",
        timeout_seconds=_optional_positive_int(raw, "timeout_seconds", default=30),
        snippet_chars=_optional_positive_int(raw, "snippet_chars", default=4000),
        app_smoke=_parse_app_smoke(raw.get("app_smoke")),
    )


def _parse_app_smoke(raw: object) -> AppSmokeSpec | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise RunSpecError("live_validation.app_smoke 必须是映射")

    target_resource_id = _optional_nonempty_str(raw, "target_resource_id")
    target_text = _optional_nonempty_str(raw, "target_text")
    target_content_desc = _optional_nonempty_str(raw, "target_content_desc")
    if not any([target_resource_id, target_text, target_content_desc]):
        raise RunSpecError(
            "live_validation.app_smoke requires at least one target surface criterion"
        )

    return AppSmokeSpec(
        package=_optional_nonempty_str(raw, "package"),
        activity=_optional_nonempty_str(raw, "activity"),
        target_resource_id=target_resource_id,
        target_text=target_text,
        target_content_desc=target_content_desc,
        app_settle_seconds=_optional_nonnegative_float(
            raw,
            "app_settle_seconds",
            default=3.0,
        ),
    )


def _validate_live_validation_context(
    live_validation: LiveValidationSpec,
    *,
    package: str,
    activity: str | None,
) -> None:
    app_smoke = live_validation.app_smoke
    if app_smoke is None:
        return
    if not (app_smoke.package or package):
        raise RunSpecError("live_validation.app_smoke.package is required")
    if not (app_smoke.activity or activity):
        raise RunSpecError(
            "live_validation.app_smoke.activity requires app_smoke.activity "
            "or top-level activity"
        )


def _parse_scenario(raw: dict[str, Any]) -> ScenarioSpec:
    scenario_id = _required_str(raw, "id")
    user_actions = _optional_str_list(raw, "user_actions")
    expected_behavior = _optional_str(raw, "expected_behavior") or ""
    metric_context = _parse_metric_context(raw.get("metric_context"))
    l3_spec = _optional_str(raw, "l3_spec") or ""
    l2_boundary_index = _optional_nonnegative_int(raw, "l2_boundary_index")

    raw_events = raw.get("system_events", [])
    if raw_events is None:
        raw_events = []
    if not isinstance(raw_events, list):
        raise RunSpecError("scenario.system_events 必须是列表")
    system_events = sorted(
        (_parse_system_event(e) for e in raw_events),
        key=lambda event: event.step_index,
    )
    if (
        l2_boundary_index is not None
        and l2_boundary_index >= len(system_events)
    ):
        raise RunSpecError(
            "scenario.l2_boundary_index does not select a configured system event"
        )

    raw_assertions = raw.get("assertions", [])
    if raw_assertions is None:
        raw_assertions = []
    if not isinstance(raw_assertions, list):
        raise RunSpecError("scenario.assertions 必须是列表")
    assertions = [_parse_assertion(a) for a in raw_assertions]

    return ScenarioSpec(
        id=scenario_id,
        user_actions=user_actions,
        system_events=system_events,
        assertions=assertions,
        l2_boundary_index=l2_boundary_index,
        expected_behavior=expected_behavior,
        metric_context=metric_context,
        l3_spec=l3_spec,
    )


def _parse_metric_context(raw: object) -> MetricContextSpec:
    if raw is None:
        return MetricContextSpec()
    if not isinstance(raw, dict):
        raise RunSpecError("scenario.metric_context 必须是映射")

    seed_kind = _optional_nonempty_str(raw, "seed_kind") or "unspecified"
    if seed_kind not in SUPPORTED_SEED_KINDS:
        allowed = ", ".join(sorted(SUPPORTED_SEED_KINDS))
        raise RunSpecError(
            f"不支持的 metric_context.seed_kind：{seed_kind}（允许：{allowed}）"
        )

    expected_oracle_level = _optional_nonempty_str(raw, "expected_oracle_level")
    if (
        expected_oracle_level is not None
        and expected_oracle_level not in SUPPORTED_ORACLE_LEVELS
    ):
        allowed = ", ".join(sorted(SUPPORTED_ORACLE_LEVELS))
        raise RunSpecError(
            f"不支持的 metric_context.expected_oracle_level："
            f"{expected_oracle_level}（允许：{allowed}）"
        )

    expected_oracle_defect_class = _optional_nonempty_str(
        raw, "expected_oracle_defect_class"
    )
    if (
        expected_oracle_defect_class is not None
        and expected_oracle_defect_class not in SUPPORTED_ORACLE_DEFECT_CLASSES
    ):
        allowed = ", ".join(sorted(SUPPORTED_ORACLE_DEFECT_CLASSES))
        raise RunSpecError(
            f"不支持的 metric_context.expected_oracle_defect_class："
            f"{expected_oracle_defect_class}（允许：{allowed}）"
        )

    return MetricContextSpec(
        seed_kind=seed_kind,
        taxonomy_category=_optional_nonempty_str(raw, "taxonomy_category"),
        taxonomy_pattern_id=_optional_nonempty_str(raw, "taxonomy_pattern_id"),
        expected_oracle_level=expected_oracle_level,
        expected_oracle_defect_class=expected_oracle_defect_class,
    )


def _parse_system_event(raw: object) -> SystemEventSpec:
    if not isinstance(raw, dict):
        raise RunSpecError("system event 必须是映射")
    step_index = raw.get("step_index")
    if not isinstance(step_index, int) or step_index < 0:
        raise RunSpecError("system event step_index 必须是非负整数")
    event = _required_str(raw, "event")
    if event not in SUPPORTED_SYSTEM_EVENTS:
        raise RunSpecError(f"不支持的 system event：{event}")
    args = raw.get("args", {})
    if args is None:
        args = {}
    if not isinstance(args, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in args.items()
    ):
        raise RunSpecError("system event args 必须是字符串映射")
    return SystemEventSpec(step_index=step_index, event=event, args=dict(args))


def _parse_assertion(raw: object) -> AssertionSpec:
    if not isinstance(raw, dict):
        raise RunSpecError("assertion 必须是映射")
    return AssertionSpec(
        resource_id=_required_str(raw, "resource_id"),
        attr=_required_str(raw, "attr"),
        expected=_required_str(raw, "expected"),
    )


def _required_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RunSpecError(f"缺少或非法字段：{key}")
    return value


def _optional_str(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RunSpecError(f"字段 {key} 必须是字符串")
    return value


def _optional_nonempty_str(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RunSpecError(f"字段 {key} 必须是非空字符串")
    return value


def _optional_nonnegative_int(data: dict[str, Any], key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or value < 0:
        raise RunSpecError(f"字段 {key} 必须是非负整数")
    return value


def _optional_positive_int(data: dict[str, Any], key: str, *, default: int) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise RunSpecError(f"字段 {key} 必须是正整数")
    return value


def _optional_nonnegative_float(
    data: dict[str, Any],
    key: str,
    *,
    default: float,
) -> float:
    value = data.get(key, default)
    if (
        not isinstance(value, int | float)
        or isinstance(value, bool)
        or value < 0
    ):
        raise RunSpecError(f"字段 {key} 必须是非负数字")
    return float(value)


def _optional_str_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(i, str) for i in value):
        raise RunSpecError(f"字段 {key} 必须是字符串列表")
    return list(value)


def _optional_path(data: dict[str, Any], key: str, *, base_dir: Path) -> Path | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RunSpecError(f"字段 {key} 必须是非空路径字符串")
    return _resolve_path(value, base_dir=base_dir)


def _resolve_path(value: str, *, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return base_dir / path
