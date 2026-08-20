import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ai_webmaster
from webmaster_models import (
    create_issue,
    merge_issue_lifecycle,
    serialize_issue,
    stable_issue_id,
    validate_issue,
)


def issue(**overrides):
    values = {
        "page": "index",
        "category": "seo",
        "issue_type": "seo_title",
        "severity": "warning",
        "title": "Hiányzó SEO cím",
        "description": "Hiányzó SEO cím.",
        "evidence": {"target": "seo.title", "field": "title", "current_value": ""},
        "detected_at": "2026-08-20T08:00:00+00:00",
        "suggested_action": {"action": "set_seo", "target": "index", "reason": "SEO cím szükséges."},
        "policy_risk": "UNKNOWN",
        "target": "seo.title",
        "legacy_severity": "medium",
    }
    values.update(overrides)
    return create_issue(**values)


def test_valid_issue_schema():
    item = issue()
    assert validate_issue(item) is item
    assert item["schema_version"] == 1
    assert item["status"] == "open"


def test_invalid_severity_rejected():
    with pytest.raises(ValueError, match="severity"):
        issue(severity="medium")


def test_invalid_status_rejected():
    with pytest.raises(ValueError, match="status"):
        issue(status="pending")


def test_stable_issue_id():
    first = stable_issue_id(page="index", category="seo", issue_type="seo_title", target="seo.title")
    second = stable_issue_id(page=" INDEX ", category="SEO", issue_type="seo_title", target="seo.title")
    assert first == second and first.startswith("wm_")


def test_same_issue_across_audits_has_same_id():
    assert issue(detected_at="2026-08-20T08:00:00+00:00")["issue_id"] == issue(
        detected_at="2026-08-21T08:00:00+00:00")["issue_id"]


def test_different_issues_have_different_ids():
    assert issue()["issue_id"] != issue(issue_type="seo_description", target="seo.description")["issue_id"]


def test_evidence_serialization_is_structured():
    loaded = json.loads(serialize_issue(issue(evidence={"target": "seo.title", "details": {"length": 0}})))
    assert loaded["evidence"]["details"]["length"] == 0


def test_suggested_action_serialization_is_structured_and_not_approval():
    loaded = json.loads(serialize_issue(issue()))
    assert loaded["suggested_action"]["action"] == "set_seo"
    assert "allowed" not in loaded["suggested_action"]


def test_unknown_policy_risk_is_valid_default():
    assert issue(suggested_action=None)["policy_risk"] == "UNKNOWN"


def _audit_fixture(tmp_path, monkeypatch, *, seo_title="", blocks=None, previous=None):
    pages_path = tmp_path / "pages.json"
    config_path = tmp_path / "automation.json"
    audit_path = tmp_path / "ai_audit.json"
    log_path = tmp_path / "ai_log.json"
    pages_path.write_text(json.dumps({"pages": {"index": {
        "seo": {"title": seo_title, "description": "Megfelelő meta leírás."},
        "fields": [], "blocks": blocks or [],
    }}}), encoding="utf-8")
    config_path.write_text(json.dumps({"booking_url": "https://recepciosai.hu/b/test"}), encoding="utf-8")
    audit_path.write_text(json.dumps(previous or {"items": []}), encoding="utf-8")
    monkeypatch.setattr(ai_webmaster, "PAGES", pages_path)
    monkeypatch.setattr(ai_webmaster, "CONFIG", config_path)
    monkeypatch.setattr(ai_webmaster, "AUDIT", audit_path)
    monkeypatch.setattr(ai_webmaster, "LOG", log_path)
    return pages_path, audit_path


def test_existing_audit_detector_compatibility(tmp_path, monkeypatch):
    _audit_fixture(tmp_path, monkeypatch)
    output = ai_webmaster.audit_site()
    item = next(x for x in output["items"] if x["type"] == "seo_title")
    assert output["summary"]["medium"] == 1
    assert item["page"] == "index" and item["message"] == "Hiányzó SEO cím."


def test_admin_backward_compatibility_fields_are_preserved(tmp_path, monkeypatch):
    _audit_fixture(tmp_path, monkeypatch)
    item = ai_webmaster.audit_site()["items"][0]
    assert all(key in item for key in ("severity", "page", "type", "message"))


def test_repeated_issue_preserves_detected_at_and_updates_last_seen(tmp_path, monkeypatch):
    _, audit_path = _audit_fixture(tmp_path, monkeypatch)
    times = iter(("2026-08-20T08:00:00+00:00", "2026-08-21T08:00:00+00:00"))
    monkeypatch.setattr(ai_webmaster, "utcnow", lambda: next(times))
    monkeypatch.setattr(ai_webmaster, "append_log", lambda *args, **kwargs: None)
    first = ai_webmaster.audit_site()["items"][0]
    second = ai_webmaster.audit_site()["items"][0]
    assert second["issue_id"] == first["issue_id"]
    assert second["detected_at"] == first["detected_at"]
    assert second["last_seen_at"] == "2026-08-21T08:00:00+00:00"
    assert len(json.loads(audit_path.read_text(encoding="utf-8"))["items"]) == 1


def test_disappeared_issue_becomes_resolved(tmp_path, monkeypatch):
    pages_path, _ = _audit_fixture(tmp_path, monkeypatch)
    times = iter(("2026-08-20T08:00:00+00:00", "2026-08-21T08:00:00+00:00"))
    monkeypatch.setattr(ai_webmaster, "utcnow", lambda: next(times))
    monkeypatch.setattr(ai_webmaster, "append_log", lambda *args, **kwargs: None)
    first = ai_webmaster.audit_site()["items"][0]
    data = json.loads(pages_path.read_text(encoding="utf-8"))
    data["pages"]["index"]["seo"]["title"] = "Fehérvitál"
    pages_path.write_text(json.dumps(data), encoding="utf-8")
    resolved = ai_webmaster.audit_site()["items"][0]
    assert resolved["issue_id"] == first["issue_id"]
    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"] == "2026-08-21T08:00:00+00:00"


def test_ignored_issue_is_preserved_on_repeated_detection():
    old = issue(status="ignored")
    merged = merge_issue_lifecycle([old], [issue()], now="2026-08-21T08:00:00+00:00")
    assert len(merged) == 1 and merged[0]["status"] == "ignored"


def test_acknowledged_issue_is_preserved_on_repeated_detection():
    merged = merge_issue_lifecycle(
        [issue(status="acknowledged")], [issue()], now="2026-08-21T08:00:00+00:00")
    assert merged[0]["status"] == "acknowledged"


def test_planned_issue_is_preserved_on_repeated_detection():
    merged = merge_issue_lifecycle(
        [issue(status="planned")], [issue()], now="2026-08-21T08:00:00+00:00")
    assert merged[0]["status"] == "planned"


def test_resolved_issue_reopens_on_repeated_detection():
    old = issue(status="resolved")
    old["resolved_at"] = "2026-08-20T12:00:00+00:00"
    merged = merge_issue_lifecycle([old], [issue()], now="2026-08-21T08:00:00+00:00")
    assert merged[0]["status"] == "open"


def test_reopened_issue_clears_resolved_at():
    old = issue(status="resolved")
    old["resolved_at"] = "2026-08-20T12:00:00+00:00"
    merged = merge_issue_lifecycle([old], [issue()], now="2026-08-21T08:00:00+00:00")
    assert merged[0]["resolved_at"] is None


def test_reopened_issue_preserves_original_detected_at():
    old = issue(status="resolved", detected_at="2026-08-19T08:00:00+00:00")
    old["resolved_at"] = "2026-08-20T12:00:00+00:00"
    merged = merge_issue_lifecycle([old], [issue()], now="2026-08-21T08:00:00+00:00")
    assert merged[0]["detected_at"] == "2026-08-19T08:00:00+00:00"


def test_disappeared_acknowledged_issue_becomes_resolved():
    merged = merge_issue_lifecycle(
        [issue(status="acknowledged")], [], now="2026-08-21T08:00:00+00:00")
    assert merged[0]["status"] == "resolved"


def test_disappeared_planned_issue_becomes_resolved():
    merged = merge_issue_lifecycle(
        [issue(status="planned")], [], now="2026-08-21T08:00:00+00:00")
    assert merged[0]["status"] == "resolved"


def test_absent_resolved_issue_preserves_original_resolved_at():
    old = issue(status="resolved")
    old["resolved_at"] = "2026-08-20T12:00:00+00:00"
    merged = merge_issue_lifecycle([old], [], now="2026-08-21T08:00:00+00:00")
    assert merged[0]["status"] == "resolved"
    assert merged[0]["resolved_at"] == "2026-08-20T12:00:00+00:00"


def test_disappeared_ignored_issue_remains_ignored():
    old = issue(status="ignored")
    merged = merge_issue_lifecycle([old], [], now="2026-08-21T08:00:00+00:00")
    assert merged[0]["status"] == "ignored"
    assert merged[0]["resolved_at"] is None


def test_duplicate_issue_is_not_created():
    merged = merge_issue_lifecycle([], [issue(), issue()], now="2026-08-21T08:00:00+00:00")
    assert len(merged) == 1


def test_secret_redaction_in_issue_content():
    secret = "sk" + "-example-secret-value-123456"
    item = issue(title=f"Leaked {secret}", description=f"Bearer {secret}",
                 evidence={"api_key": secret, "details": secret},
                 suggested_action={"action": "review", "token": secret})
    serialized = serialize_issue(item)
    assert secret not in serialized
    assert "[REDACTED]" in serialized
