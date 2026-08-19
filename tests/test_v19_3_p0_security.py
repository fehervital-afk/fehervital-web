import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import automation_policy as policy
import ai_webmaster
import autopilot
import executor_engine
import local_admin_server


def plan(change, ai_risk="low"):
    return {"summary": "test", "risk": ai_risk, "requires_approval": False, "changes": [change]}


def test_unknown_action_is_blocked():
    decision = policy.evaluate_action({"action": "invented", "target": "index", "target_type": "cms_page"})
    assert decision.risk == "BLOCKED" and not decision.allowed


def test_ai_low_cannot_downgrade_policy_medium():
    result = policy.evaluate_plan(plan({"action": "set_seo", "page": "index", "seo": {"title": "Safe"}}))
    assert result["risk"] == "MEDIUM"
    assert result["approval_required"] and not result["allowed"]


def test_protected_file_is_blocked():
    decision = policy.evaluate_action({"action": "set_field", "target": ".github/workflows/x.yml",
                                       "target_type": "cms_page", "key": "x", "value": "y"}, approved=True)
    assert decision.risk == "BLOCKED" and decision.protected


def test_protected_cms_value_is_high_and_requires_approval():
    request = {"action": "set_field", "page": "index", "key": "booking_url",
               "value": "https://recepciosai.hu/changed"}
    denied = policy.evaluate_action(request)
    approved = policy.evaluate_action(request, approved=True)
    assert denied.risk == "HIGH" and denied.protected and not denied.allowed
    assert approved.allowed and approved.approval_required


def test_medium_without_approval_is_blocked():
    decision = policy.evaluate_action({"action": "add_block", "page": "index", "block": {"type": "text"}})
    assert decision.risk == "MEDIUM" and not decision.allowed


def test_high_action_is_never_allowed_through_autopilot():
    decision = policy.evaluate_action({"action": "publish", "target": "production", "target_type": "production"},
                                      approved=True, autopilot=True)
    assert decision.risk == "BLOCKED" and not decision.allowed and not decision.autopilot_allowed


def test_low_explicit_read_only_action_is_permitted():
    decision = policy.evaluate_action({"action": "audit_site", "target": "site", "target_type": "site"}, autopilot=True)
    assert decision.allowed and decision.risk == "LOW" and decision.autopilot_allowed


def test_invalid_action_schema_fails_closed():
    assert policy.evaluate_plan({"changes": "bad"})["risk"] == "BLOCKED"
    assert not policy.evaluate_action(None).allowed


def test_autopilot_disabled_is_hard_stop_even_with_force(tmp_path, monkeypatch):
    config = tmp_path / "autopilot.json"
    config.write_text(json.dumps({"enabled": False, "stats": {}}), encoding="utf-8")
    monkeypatch.setattr(autopilot, "AUTOPILOT", config)
    monkeypatch.setattr(policy, "AUDIT_LOG", tmp_path / "audit.json")
    result = autopilot.run_once(force=True)
    assert result["status"] == "disabled"


def test_force_auto_cannot_bypass_policy(tmp_path, monkeypatch):
    pages_path = tmp_path / "pages.json"
    tasks_path = tmp_path / "tasks.json"
    config_path = tmp_path / "automation.json"
    pages = {"pages": {"index": {"fields": [{"key": "hero", "value": "before"}], "blocks": []}}}
    task = {"id": "t1", "prompt": "change", "status": "pending"}
    pages_path.write_text(json.dumps(pages), encoding="utf-8")
    tasks_path.write_text(json.dumps({"tasks": [task]}), encoding="utf-8")
    config_path.write_text(json.dumps({"enabled": True, "mode": "safe_auto"}), encoding="utf-8")
    monkeypatch.setattr(ai_webmaster, "PAGES", pages_path)
    monkeypatch.setattr(ai_webmaster, "TASKS", tasks_path)
    monkeypatch.setattr(ai_webmaster, "CONFIG", config_path)
    monkeypatch.setattr(ai_webmaster, "LOG", tmp_path / "ai_log.json")
    monkeypatch.setattr(policy, "AUDIT_LOG", tmp_path / "audit.json")
    monkeypatch.setattr(policy, "PAGES_JSON", pages_path)
    output = plan({"action": "set_field", "page": "index", "key": "hero", "value": "after"})
    monkeypatch.setattr(ai_webmaster, "call_openai", lambda *_: json.dumps(output))
    result = ai_webmaster.process_tasks(force_auto=True)
    assert result[0]["status"] == "waiting_approval"
    assert json.loads(pages_path.read_text(encoding="utf-8"))["pages"]["index"]["fields"][0]["value"] == "before"


def _executor_fixture(tmp_path, monkeypatch, action):
    pages_path = tmp_path / "pages.json"
    tasks_path = tmp_path / "tasks.json"
    queue_path = tmp_path / "queue.json"
    backups = tmp_path / "backups"
    pages = {"pages": {"index": {"fields": [{"key": "hero", "value": "before"}], "blocks": [], "seo": {}}}}
    item = {"id": "e1", "task_id": "t1", "status": "ready", "plan": plan(action), "summary": "test"}
    pages_path.write_text(json.dumps(pages), encoding="utf-8")
    tasks_path.write_text(json.dumps({"tasks": [{"id": "t1", "status": "waiting_approval"}]}), encoding="utf-8")
    queue_path.write_text(json.dumps({"settings": {"create_backup_before_apply": True}, "items": [item], "history": []}), encoding="utf-8")
    monkeypatch.setattr(executor_engine, "PAGES", pages_path)
    monkeypatch.setattr(executor_engine, "TASKS", tasks_path)
    monkeypatch.setattr(executor_engine, "QUEUE", queue_path)
    monkeypatch.setattr(executor_engine, "BACKUPS", backups)
    monkeypatch.setattr(executor_engine, "ROOT", tmp_path)
    monkeypatch.setattr(policy, "AUDIT_LOG", tmp_path / "audit.json")
    monkeypatch.setattr(policy, "PAGES_JSON", pages_path)
    return pages_path, queue_path


def test_executor_rechecks_and_blocks_unknown_action(tmp_path, monkeypatch):
    _, queue_path = _executor_fixture(tmp_path, monkeypatch, {"action": "unknown", "page": "index"})
    with pytest.raises(SystemExit, match="Policy blocked"):
        executor_engine.secure_approve("e1")
    assert json.loads(queue_path.read_text(encoding="utf-8"))["items"][0]["status"] == "blocked"


def test_failed_validation_sets_status_and_rolls_back(tmp_path, monkeypatch):
    pages_path, queue_path = _executor_fixture(
        tmp_path, monkeypatch, {"action": "set_field", "page": "index", "key": "hero", "value": "after"})
    monkeypatch.setattr(executor_engine, "run_validation", lambda: {"ok": False, "results": [{"returncode": 1}]})
    result = executor_engine.secure_approve("e1", actor="human")
    assert result["status"] == "validation_failed"
    assert json.loads(queue_path.read_text(encoding="utf-8"))["items"][0]["status"] == "validation_failed"
    assert json.loads(pages_path.read_text(encoding="utf-8"))["pages"]["index"]["fields"][0]["value"] == "before"


def test_audit_event_is_written_and_secrets_are_redacted(tmp_path):
    audit = tmp_path / "audit.json"
    policy.write_audit_event("task_created", task_id="t1", actor="test", result="ok",
                             details={"OPENAI_API_KEY": "sk-supersecretvalue"}, path=audit)
    text = audit.read_text(encoding="utf-8")
    assert "task_created" in text and "sk-supersecretvalue" not in text and "[REDACTED]" in text


def test_admin_rejects_unsafe_origin_and_accepts_valid_localhost():
    token = local_admin_server.ADMIN_CSRF_TOKEN
    assert not local_admin_server.local_admin_request_allowed("127.0.0.1:8000", "https://evil.example", token)
    assert not local_admin_server.local_admin_request_allowed("127.0.0.1:8000", "http://127.0.0.1:8000", "wrong")
    assert local_admin_server.local_admin_request_allowed("localhost:8000", "http://localhost:8000", token)


def test_security_data_is_not_in_public_build_manifest():
    build_source = (SCRIPTS / "build_public.py").read_text(encoding="utf-8")
    assert "automation_audit.json" not in build_source
    assert "automation_policy.py" not in build_source
    assert "assets/content/pages.json" in build_source


def _write_policy_pages(tmp_path, value):
    pages_path = tmp_path / "pages.json"
    pages_path.write_text(json.dumps({"pages": {"index": {
        "fields": [{"key": "hero_lead", "value": value}], "blocks": [], "seo": {}
    }}}), encoding="utf-8")
    return pages_path


def test_protected_current_email_cannot_be_downgraded_by_replacement(tmp_path, monkeypatch):
    monkeypatch.setattr(policy, "PAGES_JSON", _write_policy_pages(tmp_path, "info@fehervital.hu"))
    request = {"action": "set_field", "page": "index", "key": "hero_lead", "value": "other@example.com"}
    denied = policy.evaluate_action(request)
    approved = policy.evaluate_action(request, approved=True)
    assert denied.risk == "HIGH" and denied.protected and not denied.allowed
    assert approved.risk == "HIGH" and approved.allowed and approved.approval_required


def test_protected_current_booking_url_remains_high_when_replaced(tmp_path, monkeypatch):
    monkeypatch.setattr(policy, "PAGES_JSON", _write_policy_pages(
        tmp_path, "https://recepciosai.hu/b/fehervital-egeszsegpont"))
    request = {"action": "set_field", "page": "index", "key": "hero_lead", "value": "https://example.com/new"}
    decision = policy.evaluate_action(request)
    assert decision.risk == "HIGH" and decision.protected and decision.approval_required


def test_publish_arbitrary_production_target_is_blocked():
    decision = policy.evaluate_action({"action": "publish", "target": "other-production",
                                       "target_type": "production"}, approved=True, actor="local_admin")
    assert decision.risk == "BLOCKED" and not decision.allowed


def test_publish_is_blocked_for_autopilot_even_on_canonical_target():
    decision = policy.evaluate_action({"action": "publish", "target": "production",
                                       "target_type": "production"}, approved=True,
                                      actor="local_admin", autopilot=True)
    assert decision.risk == "BLOCKED" and not decision.allowed


def test_audit_site_requires_canonical_target():
    canonical = policy.evaluate_action({"action": "audit_site", "target": "site", "target_type": "site"},
                                       autopilot=True)
    unknown = policy.evaluate_action({"action": "audit_site", "target": "external-site", "target_type": "site"},
                                     autopilot=True)
    assert canonical.allowed and canonical.risk == "LOW"
    assert unknown.risk == "BLOCKED" and not unknown.allowed


def test_current_value_lookup_rejects_traversal_before_any_file_read(monkeypatch):
    class MustNotRead:
        def read_text(self, *args, **kwargs):
            raise AssertionError("Policy attempted an arbitrary file read")

    monkeypatch.setattr(policy, "PAGES_JSON", MustNotRead())
    decision = policy.evaluate_action({"action": "set_field", "page": "../../secret",
                                       "key": "hero_lead", "value": "replacement"}, approved=True)
    assert decision.risk == "BLOCKED" and not decision.allowed


def test_local_admin_autopilot_run_has_no_force_and_keeps_hard_stops(tmp_path, monkeypatch):
    source = (ROOT / "local_admin_server.py").read_text(encoding="utf-8")
    endpoint = source.split("if self.path == '/__admin/autopilot-run':", 1)[1].split(
        "if self.path == '/__admin/autopilot-settings':", 1
    )[0]
    assert "'--run'" in endpoint
    assert "--force" not in endpoint

    config = tmp_path / "autopilot.json"
    config.write_text(json.dumps({"enabled": False, "mode": "observe", "stats": {}}), encoding="utf-8")
    monkeypatch.setattr(autopilot, "AUTOPILOT", config)
    monkeypatch.setattr(policy, "AUDIT_LOG", tmp_path / "audit.json")
    assert autopilot.run_once(force=False)["status"] == "disabled"

    mutating = policy.evaluate_plan(
        plan({"action": "add_block", "page": "index", "block": {"type": "text"}}),
        approved=False,
        actor="autopilot",
        autopilot=True,
    )
    assert not mutating["allowed"] and not mutating["autopilot_allowed"]
