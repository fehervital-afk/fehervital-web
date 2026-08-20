import copy
import ast
import json
import socket
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ai_webmaster
from webmaster_audit import detect_issues
from webmaster_models import merge_issue_lifecycle, serialize_issue

NOW = "2026-08-20T08:00:00+00:00"
CONFIG = {"booking_url": "https://recepciosai.hu/b/fehervital-egeszsegpont"}


def valid_cms(*, fields=None, blocks=None):
    return {"pages": {"index": {
        "seo": {"title": "Fehérvitál", "description": "Megfelelő meta leírás."},
        "fields": fields if fields is not None else [{"key": "title", "value": "Főoldal"}],
        "blocks": blocks if blocks is not None else [],
    }}}


def audit(cms, tmp_path, config=CONFIG):
    return detect_issues(cms, config, project_root=tmp_path, detected_at=NOW)


def types(items):
    return [item["type"] for item in items]


def test_valid_cms_has_no_schema_issue(tmp_path):
    assert not [item for item in audit(valid_cms(), tmp_path) if item["category"] == "technical"]


def test_malformed_root_is_reported_without_crash(tmp_path):
    assert types(audit([], tmp_path)) == ["malformed_cms_root"]


def test_malformed_pages_is_reported(tmp_path):
    assert types(audit({"pages": []}, tmp_path)) == ["malformed_pages"]


def test_malformed_page_is_reported(tmp_path):
    assert "malformed_page" in types(audit({"pages": {"index": []}}, tmp_path))


def test_malformed_fields_is_reported(tmp_path):
    cms = valid_cms()
    cms["pages"]["index"]["fields"] = {}
    assert "malformed_fields" in types(audit(cms, tmp_path))


def test_malformed_blocks_is_reported(tmp_path):
    cms = valid_cms()
    cms["pages"]["index"]["blocks"] = {}
    assert "malformed_blocks" in types(audit(cms, tmp_path))


def test_malformed_block_is_reported(tmp_path):
    assert "malformed_block" in types(audit(valid_cms(blocks=["bad"]), tmp_path))


def test_supported_block_required_structure_is_checked(tmp_path):
    items = audit(valid_cms(blocks=[{"id": "faq-1", "type": "faq"}]), tmp_path)
    assert "malformed_block_structure" in types(items)


def test_proven_required_empty_field_is_reported(tmp_path):
    items = audit(valid_cms(fields=[{"key": "title", "value": "  "}]), tmp_path)
    assert "required_content_empty" in types(items)


def test_optional_empty_field_is_not_reported(tmp_path):
    items = audit(valid_cms(fields=[{"key": "note", "value": ""}]), tmp_path)
    assert "required_content_empty" not in types(items)


def test_image_missing_src_is_reported(tmp_path):
    items = audit(valid_cms(blocks=[{"id": "hero-image", "type": "image", "alt": "Hero"}]), tmp_path)
    assert "image_missing_src" in types(items)


def test_image_missing_local_file_is_reported(tmp_path):
    items = audit(valid_cms(blocks=[{"id": "hero-image", "type": "image",
                                    "src": "assets/uploads/missing.png", "alt": "Hero"}]), tmp_path)
    assert "missing_media" in types(items)


def test_video_missing_source_is_reported(tmp_path):
    items = audit(valid_cms(blocks=[{"id": "intro-video", "type": "video", "src": ""}]), tmp_path)
    assert "video_missing_source" in types(items)


def test_video_missing_local_file_is_reported(tmp_path):
    items = audit(valid_cms(blocks=[{"id": "intro-video", "type": "video",
                                    "src": "assets/uploads/missing.mp4"}]), tmp_path)
    assert "missing_media" in types(items)


def test_video_src_local_existing_is_valid(tmp_path):
    media = tmp_path / "assets/uploads/video.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"video")
    items = audit(valid_cms(blocks=[{"id": "video", "type": "video",
                                    "src": "assets/uploads/video.mp4"}]), tmp_path)
    assert "missing_media" not in types(items)
    assert "unsafe_media_path" not in types(items)


def test_video_url_external_https_is_valid_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    items = audit(valid_cms(blocks=[{"id": "video", "type": "video",
                                    "url": "https://video.example/watch/1"}]), tmp_path)
    assert not {"video_missing_source", "missing_media", "unsafe_media_path"}.intersection(types(items))


def test_video_url_external_http_skips_filesystem_and_keeps_insecure_detector(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(Path, "is_file", lambda self: calls.append(self) or False)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    items = audit(valid_cms(blocks=[{"id": "video", "type": "video",
                                    "url": "http://video.example/watch/1"}]), tmp_path)
    assert all(path.suffix == ".html" for path in calls)
    assert "insecure_link" in types(items)
    assert "missing_media" not in types(items)


def test_video_url_local_existing_is_valid_and_reports_url_field(tmp_path):
    media = tmp_path / "assets/uploads/video.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"video")
    items = audit(valid_cms(blocks=[{"id": "video", "type": "video",
                                    "url": "assets/uploads/video.mp4"}]), tmp_path)
    assert "missing_media" not in types(items)
    assert "video_missing_source" not in types(items)


def test_video_url_local_missing_reports_url_field_and_target(tmp_path):
    items = audit(valid_cms(blocks=[{"id": "video", "type": "video",
                                    "url": "assets/uploads/missing.mp4"}]), tmp_path)
    missing = next(item for item in items if item["type"] == "missing_media")
    assert missing["evidence"]["field"] == "url"
    assert missing["evidence"]["target"] == "blocks.id.video.url"


def test_video_src_takes_precedence_over_url(tmp_path):
    media = tmp_path / "assets/uploads/from-src.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"video")
    items = audit(valid_cms(blocks=[{"id": "video", "type": "video",
                                    "src": "assets/uploads/from-src.mp4",
                                    "url": "assets/uploads/missing-url.mp4"}]), tmp_path)
    assert "missing_media" not in types(items)


def test_video_missing_src_and_url_reports_video_missing_source(tmp_path):
    items = audit(valid_cms(blocks=[{"id": "video", "type": "video"}]), tmp_path)
    assert "video_missing_source" in types(items)


def test_image_url_without_src_still_reports_image_missing_src(tmp_path):
    items = audit(valid_cms(blocks=[{"id": "image", "type": "image",
                                    "url": "https://images.example/image.png", "alt": "Image"}]), tmp_path)
    assert "image_missing_src" in types(items)


def test_empty_hero_title_is_required_content_issue(tmp_path):
    items = audit(valid_cms(fields=[{"key": "hero_title", "value": ""}]), tmp_path)
    assert "required_content_empty" in types(items)


def test_path_traversal_is_blocked_before_file_lookup(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(Path, "is_file", lambda self: calls.append(self) or False)
    items = audit(valid_cms(blocks=[{"id": "unsafe", "type": "image",
                                    "src": "assets/uploads/../../.env", "alt": "x"}]), tmp_path)
    assert "unsafe_media_path" in types(items)
    assert not any(".env" in str(path) for path in calls)


def test_absolute_external_path_is_blocked_before_file_lookup(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(Path, "is_file", lambda self: calls.append(self) or False)
    items = audit(valid_cms(blocks=[{"id": "unsafe", "type": "video",
                                    "src": "C:/Windows/System32/config/SAM"}]), tmp_path)
    assert "unsafe_media_path" in types(items)
    assert not any("System32" in str(path) for path in calls)


def test_external_video_url_is_not_fetched_or_treated_as_local(tmp_path, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    items = audit(valid_cms(blocks=[{"id": "remote-video", "type": "video",
                                    "src": "https://video.example/watch/1"}]), tmp_path)
    assert "missing_media" not in types(items)
    assert "unsafe_media_path" not in types(items)


def test_stable_block_id_produces_stable_issue_id(tmp_path):
    cms = valid_cms(blocks=[{"id": "hero-image", "type": "image", "src": ""}])
    first = next(item for item in audit(cms, tmp_path) if item["type"] == "image_missing_src")
    second = next(item for item in audit(copy.deepcopy(cms), tmp_path) if item["type"] == "image_missing_src")
    assert first["issue_id"] == second["issue_id"]


def test_duplicate_prevention_uses_existing_lifecycle_merge(tmp_path):
    item = audit(valid_cms(blocks=[{"id": "hero-image", "type": "image", "src": ""}]), tmp_path)[0]
    assert len(merge_issue_lifecycle([], [item, copy.deepcopy(item)], now=NOW)) == 1


def test_lifecycle_compatibility_preserves_acknowledged(tmp_path):
    current = audit(valid_cms(blocks=[{"id": "hero-image", "type": "image", "src": ""}]), tmp_path)[0]
    old = copy.deepcopy(current)
    old["status"] = "acknowledged"
    old["detected_at"] = "2026-08-19T08:00:00+00:00"
    merged = merge_issue_lifecycle([old], [current], now=NOW)
    assert merged[0]["status"] == "acknowledged"
    assert merged[0]["detected_at"] == old["detected_at"]


def test_secret_redaction_applies_to_detector_evidence(tmp_path):
    secret = "sk" + "-example-secret-value-123456"
    cms = valid_cms(fields=[{"key": "note", "value": f"http://example.test/?api_key={secret}"}])
    serialized = serialize_issue(audit(cms, tmp_path)[0])
    assert secret not in serialized
    assert "[REDACTED]" in serialized


def test_engine_does_not_mutate_cms_or_config(tmp_path):
    cms = valid_cms(blocks=[{"id": "hero-image", "type": "image", "src": ""}])
    config = copy.deepcopy(CONFIG)
    before = json.dumps({"cms": cms, "config": config}, sort_keys=True)
    audit(cms, tmp_path, config)
    assert json.dumps({"cms": cms, "config": config}, sort_keys=True) == before


def test_engine_does_not_mutate_public_or_security_files():
    protected = [
        ROOT / "assets/content/pages.json",
        ROOT / "scripts/automation_policy.py", ROOT / "scripts/executor_engine.py",
    ]
    protected += sorted(ROOT.glob("*.html"))
    protected += sorted((ROOT / ".github/workflows").glob("*.yml"))
    uploads = sorted((ROOT / "assets/uploads").glob("**/*"))
    before = {path: path.read_bytes() for path in protected + [p for p in uploads if p.is_file()]}
    cms = json.loads((ROOT / "assets/content/pages.json").read_text(encoding="utf-8"))
    detect_issues(cms, CONFIG, project_root=ROOT, detected_at=NOW)
    after = {path: path.read_bytes() for path in before}
    assert after == before


def test_engine_has_no_network_subprocess_or_ai_sdk_dependencies():
    source = (SCRIPTS / "webmaster_audit.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    forbidden = {"http", "requests", "httpx", "socket", "subprocess",
                 "openai", "google", "anthropic"}
    assert imports.isdisjoint(forbidden)
    assert "urllib.request" not in source
    assert "gemini" not in source.lower()


def test_existing_detector_regression(tmp_path):
    cms = valid_cms(
        fields=[{"key": "title", "value": "Főoldal"},
                {"key": "note", "value": "http://example.test"}],
        blocks=[{"id": "image-1", "type": "image",
                 "src": "assets/uploads/missing.png", "alt": ""}],
    )
    cms["pages"]["index"]["seo"] = {"title": "", "description": ""}
    found = set(types(audit(cms, tmp_path, config={})))
    assert {"seo_title", "seo_description", "insecure_link", "alt_text",
            "missing_media", "booking_url"}.issubset(found)


def test_ai_webmaster_integration_writes_only_audit_state(tmp_path, monkeypatch):
    pages_path = tmp_path / "pages.json"
    config_path = tmp_path / "automation.json"
    audit_path = tmp_path / "ai_audit.json"
    log_path = tmp_path / "ai_log.json"
    pages_path.write_text(json.dumps(valid_cms()), encoding="utf-8")
    config_path.write_text(json.dumps(CONFIG), encoding="utf-8")
    before = pages_path.read_bytes()
    monkeypatch.setattr(ai_webmaster, "PAGES", pages_path)
    monkeypatch.setattr(ai_webmaster, "CONFIG", config_path)
    monkeypatch.setattr(ai_webmaster, "AUDIT", audit_path)
    monkeypatch.setattr(ai_webmaster, "LOG", log_path)
    monkeypatch.setattr(ai_webmaster, "ROOT", tmp_path)
    ai_webmaster.audit_site()
    assert pages_path.read_bytes() == before
    assert audit_path.is_file() and log_path.is_file()
