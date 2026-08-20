import ast
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from webmaster_proposals import (
    CurrentSnapshot,
    PolicySnapshot,
    Proposal,
    canonical_json,
    create_proposal,
    deserialize_proposal,
    evidence_hash,
    payload_hash,
    serialize_proposal,
    snapshot_hash,
    stable_proposal_id,
)

STAMP = "2026-08-20T10:00:00+00:00"


def proposal(**overrides):
    payload = overrides.pop("payload", {"key": "hero_title", "value": "Fehérvitál"})
    values = {
        "issue_id": "wm_0123456789abcdef",
        "issue_type": "required_content_empty",
        "source": "deterministic",
        "disposition": "proposable",
        "action": "set_field",
        "target": "index",
        "payload": payload,
        "reason": "A bizonyítottan kötelező mező üres.",
        "current_snapshot": CurrentSnapshot(
            resource="assets/content/pages.json",
            value_hash=payload_hash(""),
            resource_hash=snapshot_hash({"pages": {}}),
        ),
        "evidence_hash_value": evidence_hash({"field": "hero_title"}),
        "policy": PolicySnapshot(
            risk="MEDIUM", approval_required=True, autopilot_allowed=False,
            decision="needs_human_approval", reason="Emberi jóváhagyás szükséges.",
        ),
        "status": "needs_review",
        "created_at": STAMP,
        "updated_at": STAMP,
    }
    values.update(overrides)
    return create_proposal(**values)


def test_valid_proposal_and_nested_models():
    item = proposal()
    assert item.proposal_version == 1
    assert item.current_snapshot.resource == "assets/content/pages.json"
    assert item.policy.autopilot_allowed is False


def test_stable_id_is_timestamp_independent_and_target_normalized():
    first = proposal(created_at=STAMP, updated_at=STAMP)
    second = proposal(created_at="2026-08-21T10:00:00+00:00",
                      updated_at="2026-08-21T10:00:00+00:00", target=" INDEX ")
    assert first.proposal_id == second.proposal_id


def test_dict_order_and_nested_dict_are_canonical():
    one = proposal(payload={"outer": {"a": 1, "b": 2}, "z": 3})
    two = proposal(payload={"z": 3, "outer": {"b": 2, "a": 1}})
    assert one.proposal_id == two.proposal_id


def test_list_order_payload_case_and_payload_change_affect_identity():
    assert proposal(payload={"x": [1, 2]}).proposal_id != proposal(payload={"x": [2, 1]}).proposal_id
    assert proposal(payload={"value": "Foo"}).proposal_id != proposal(payload={"value": "foo"}).proposal_id
    assert proposal(payload={"value": "a"}).proposal_id != proposal(payload={"value": "b"}).proposal_id


def test_unicode_is_preserved_and_bool_does_not_equal_int():
    assert "Fehérvitál" in proposal().to_json()
    assert proposal(payload={"x": True}).proposal_id != proposal(payload={"x": 1}).proposal_id


@pytest.mark.parametrize("bad", [{"x": object()}, {"x": math.nan}, {"x": math.inf}, {1: "x"}])
def test_malformed_or_non_finite_payload_rejected(bad):
    with pytest.raises(ValueError):
        proposal(payload=bad)


@pytest.mark.parametrize("field,value", [
    ("source", "robot"), ("disposition", "automatic"), ("status", "executed"),
])
def test_invalid_enums_rejected(field, value):
    with pytest.raises(ValueError):
        proposal(**{field: value})


def test_invalid_hash_version_and_missing_field_rejected():
    data = proposal().to_dict()
    data["evidence_hash"] = "bad"
    with pytest.raises(ValueError):
        Proposal.from_dict(data)
    data = proposal().to_dict()
    data["proposal_version"] = 2
    with pytest.raises(ValueError):
        Proposal.from_dict(data)
    data = proposal().to_dict()
    del data["reason"]
    with pytest.raises(ValueError):
        Proposal.from_dict(data)


@pytest.mark.parametrize("target", ["", "../secret", "foo/../bar", "/absolute", "C:\\secret", "\\\\server\\share", "https://x"])
def test_invalid_arbitrary_targets_rejected(target):
    with pytest.raises(ValueError):
        proposal(target=target)


def test_round_trip_and_deterministic_json():
    item = proposal(payload={"b": 2, "a": ["ő", 1]})
    encoded = serialize_proposal(item)
    decoded = deserialize_proposal(encoded)
    assert decoded == item
    assert encoded == decoded.to_json()
    assert encoded.index('"action"') < encoded.index('"created_at"')


def test_secret_redaction_is_display_only_and_does_not_merge_identity():
    secret_one = "sk" + "-example-secret-value-111111"
    secret_two = "sk" + "-example-secret-value-222222"
    first = proposal(payload={"api_key": secret_one}, reason=f"Bearer {secret_one}")
    second = proposal(payload={"api_key": secret_two}, reason=f"Bearer {secret_two}")
    assert first.proposal_id != second.proposal_id
    assert first.proposal_id == stable_proposal_id(
        issue_id=first.issue_id, action=first.action, target=first.target, payload=first.payload)
    display = serialize_proposal(first, display=True)
    assert secret_one not in display and "[REDACTED]" in display


def test_snapshot_and_policy_schema_are_fail_closed():
    with pytest.raises(ValueError):
        CurrentSnapshot.from_dict({"resource": "x", "value_hash": "0" * 64})
    with pytest.raises(ValueError):
        PolicySnapshot.from_dict({"risk": "MEDIUM"})
    with pytest.raises(ValueError, match="autopilot_allowed"):
        PolicySnapshot("MEDIUM", True, 0, "review", "reason")


def test_json_parser_rejects_nan_and_infinity():
    encoded = proposal().to_json().replace('"payload":{', '"payload":{"bad":NaN,')
    with pytest.raises(ValueError):
        deserialize_proposal(encoded)


def test_module_has_no_forbidden_imports_or_side_effect_calls():
    source = (SCRIPTS / "webmaster_proposals.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not imports.intersection({
        "executor_engine", "autopilot", "subprocess", "requests", "urllib", "httpx",
        "openai", "anthropic", "google", "build_public",
    })
    assert "write_text(" not in source
    assert "write_bytes(" not in source
    assert "Path(" not in source
    assert "publish(" not in source


def test_model_usage_does_not_mutate_repository(tmp_path):
    marker = tmp_path / "untouched"
    before = set(ROOT.rglob("*"))
    proposal().to_json(display=True)
    after = set(ROOT.rglob("*"))
    assert before == after
    assert not marker.exists()


def test_p1_3a_files_are_not_in_public_build_manifest():
    build_source = (SCRIPTS / "build_public.py").read_text(encoding="utf-8")
    assert "webmaster_proposals.py" not in build_source
    assert "test_v19_3_p1_3a_proposal_model.py" not in build_source
