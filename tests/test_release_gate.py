"""Release gate (deterministic, no model): the Validation Engine and Routing Policy must keep catching every planted
structural defect on the frozen intake set, with no false alarms, and the policy must reproduce every gold route.
A change to configs/policy.yaml or src/agreement that breaks this cannot ship (MAS AI RM Guidelines 5.14, 5.18)."""
import json
from pathlib import Path

import pytest

from src.agreement.library import load_library
from src.agreement.validation import check_request, route

ROOT = Path(__file__).resolve().parents[1]
ITEMS = [json.loads(line) for line in (ROOT / "data" / "synthetic" / "intake.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
STRUCTURAL = {"missing_field", "date_conflict", "out_of_range", "governing_law", "name_mismatch", "prompt_injection"}


@pytest.mark.parametrize("item", ITEMS, ids=[i["request_id"] for i in ITEMS])
def test_rules_catch_planted_defects_without_false_alarms(item):
    lib = load_library()
    found = {i["type"] for i in check_request(lib, item["agreement_type"], item["form"], item["text"])}
    planted = {d["type"] for d in item["defects"]} & STRUCTURAL
    assert planted <= found, f"missed {planted - found}"
    assert found <= planted, f"false alarm {found - planted}"


@pytest.mark.parametrize("item", ITEMS, ids=[i["request_id"] for i in ITEMS])
def test_policy_reproduces_gold_route(item):
    lib = load_library()
    assert route(lib, item["defects"], item["material_deviation"]) == item["gold_route"]


def test_frozen_test_split_unchanged():
    import hashlib
    test = [r for r in ITEMS if r["split"] == "test"]
    blob = "\n".join(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in test).encode("utf-8")
    assert hashlib.sha256(blob).hexdigest() == "8b7d34a28cfd67aed6b8ffc907974162df114929709b4d6df52c85302196fc5a"
