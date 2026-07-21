import copy
import json
from pathlib import Path

from aiverify.bench.concurrency_slice import judge_concurrency
from aiverify.runner.run_spec import load_run_spec


CONTRACT = json.loads(Path("bench/capability-slices/deterministic-concurrency/contract.json").read_text())


def evidence(schedule="new-before-old"):
    declaration = next(item for item in CONTRACT["schedules"] if item["id"] == schedule)
    decision = "REJECT_STALE" if schedule == "new-before-old" else "REJECT_DESTROYED"
    names = declaration["required_events"][:-1] + [decision, "TERMINAL"]
    return {
        "schedule_id": schedule,
        "identity": {"serial": "emulator-5554", "api_level": 35, "local_apk_sha256": "abc", "installed_apk_sha256": "abc"},
        "runtime": {"crashes": 0, "anrs": 0, "cleanup_exit": 0, "completed": True},
        "journal": [{"sequence": i, "schedule_id": schedule, "event": name} for i, name in enumerate(names, 1)],
        "final_state": "new" if schedule == "new-before-old" else "cancelled",
    }


def test_baseline_ordering_and_lifecycle_schedules_are_supported():
    assert judge_concurrency(CONTRACT, evidence())["conclusion"] == "locally_supported"
    assert judge_concurrency(CONTRACT, evidence("destroy-before-release"))["conclusion"] == "locally_supported"


def test_stale_and_post_destroy_candidates_are_rejected():
    stale = evidence(); stale["journal"][8]["event"] = "APPLY_STALE"; stale["final_state"] = "old"
    assert judge_concurrency(CONTRACT, stale)["findings"] == ["stale_result_applied"]
    destroyed = evidence("destroy-before-release"); destroyed["journal"][6]["event"] = "APPLY_AFTER_DESTROY"; destroyed["final_state"] = "pending"
    assert judge_concurrency(CONTRACT, destroyed)["findings"] == ["application_after_destroy"]


def test_identity_runtime_and_cleanup_fail_closed():
    cases = []
    wrong_api = evidence(); wrong_api["identity"]["api_level"] = 34; cases.append((wrong_api, "non_accountable"))
    wrong_apk = evidence(); wrong_apk["identity"]["installed_apk_sha256"] = "other"; cases.append((wrong_apk, "non_accountable"))
    cleanup = evidence(); cleanup["runtime"]["cleanup_exit"] = 1; cases.append((cleanup, "non_accountable"))
    crash = evidence(); crash["runtime"]["crashes"] = 1; cases.append((crash, "locally_rejected"))
    for item, conclusion in cases:
        assert judge_concurrency(CONTRACT, item)["conclusion"] == conclusion


def test_missing_duplicate_unknown_and_wrong_order_are_non_accountable():
    mutations = []
    missing = evidence(); missing["journal"].pop(4); mutations.append(missing)
    duplicate = evidence(); duplicate["journal"][4]["event"] = "RELEASE_NEW"; mutations.append(duplicate)
    unknown = evidence(); unknown["journal"][4]["event"] = "SURPRISE"; mutations.append(unknown)
    order = evidence(); order["journal"][3], order["journal"][4] = order["journal"][4], order["journal"][3]; mutations.append(order)
    sequence = evidence(); sequence["journal"][3]["sequence"] = 99; mutations.append(sequence)
    for item in mutations:
        assert judge_concurrency(CONTRACT, item)["conclusion"] == "non_accountable"


def test_wrong_terminal_state_and_unfinished_execution_are_non_accountable():
    wrong = evidence(); wrong["final_state"] = "old"
    assert judge_concurrency(CONTRACT, wrong)["conclusion"] == "locally_rejected"
    unfinished = evidence(); unfinished["runtime"]["completed"] = False
    assert judge_concurrency(CONTRACT, unfinished)["conclusion"] == "non_accountable"


def test_run_specs_are_matched_and_candidate_patches_are_narrow():
    root = Path("bench/capability-slices/deterministic-concurrency")
    specs = [load_run_spec(root / "run-specs" / name) for name in ("baseline.yaml", "stale-candidate.yaml", "destroy-candidate.yaml")]
    assert specs[0].scenario.user_actions == specs[1].scenario.user_actions == specs[2].scenario.user_actions
    assert specs[0].scenario.assertions == specs[1].scenario.assertions == specs[2].scenario.assertions
    assert specs[0].diff is None
    assert "APPLY_STALE" in specs[1].diff.read_text()
    assert "APPLY_AFTER_DESTROY" in specs[2].diff.read_text()
