import copy
import json
import socket
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from webmaster_audit import (
    PUBLIC_CMS_PAGE_CONTRACT, SUPPORTED_BLOCK_TYPES, build_html_link_index,
    detect_cms_html_bindings, detect_issues,
)
from webmaster_models import merge_issue_lifecycle, serialize_issue

NOW = "2026-08-20T08:00:00+00:00"
CONFIG = {"booking_url": "https://recepciosai.hu/b/test"}


def page(fields=None, blocks=None, enabled=True):
    return {"enabled": enabled, "seo": {"title": "Valid title", "description": "Valid description"},
            "fields": fields or [], "blocks": blocks or []}


def cms(**pages):
    return {"pages": pages}


def write_html(root, name, body):
    path = root / name
    path.write_text(body, encoding="utf-8")


def binding_issues(root, data):
    docs = build_html_link_index(root)
    return detect_cms_html_bindings(data, detected_at=NOW, documents=docs)


def types(items):
    return [item["type"] for item in items]


def test_renderer_contract_is_explicit_and_complete():
    assert SUPPORTED_BLOCK_TYPES == {"text", "image", "video", "iconbox", "testimonial",
                                     "price", "divider", "buttons", "cta", "faq"}
    assert "index" in PUBLIC_CMS_PAGE_CONTRACT and "lagy_lezer" in PUBLIC_CMS_PAGE_CONTRACT


def test_valid_explicit_mount_and_field_binding(tmp_path):
    write_html(tmp_path, "ai.html", '<main data-cms-page="ai"><h1 data-cms-field="title"></h1></main>')
    assert binding_issues(tmp_path, cms(ai=page([{"key": "title", "value": "AI"}]))) == []


def test_cms_page_without_public_mount(tmp_path):
    found = binding_issues(tmp_path, cms(ai=page()))
    assert "cms_page_without_public_html" in types(found)


def test_unknown_cms_page_without_contract_is_not_inferred(tmp_path):
    assert binding_issues(tmp_path, cms(arbitrary_slug=page())) == []


def test_html_mount_with_unknown_cms_slug(tmp_path):
    write_html(tmp_path, "ai.html", '<div data-cms-page="unknown"></div>')
    found = binding_issues(tmp_path, cms())
    assert types(found) == ["public_html_without_expected_cms_page"]
    assert found[0]["severity"] == "error"


def test_static_index_without_mount_is_not_finding(tmp_path):
    write_html(tmp_path, "index.html", "<main>Maintenance</main>")
    assert binding_issues(tmp_path, cms()) == []


def test_index_maps_explicitly_to_preview(tmp_path):
    write_html(tmp_path, "index.html", "<main>Maintenance</main>")
    write_html(tmp_path, "preview.html", '<main data-cms-page="index"><h1 data-cms-field="hero_title"></h1></main>')
    assert binding_issues(tmp_path, cms(index=page([{"key": "hero_title", "value": "Home"}], enabled=False))) == []


def test_slug_different_from_filename_uses_explicit_mount(tmp_path):
    write_html(tmp_path, "lagy-lezer.html", '<div data-cms-page="lagy_lezer"></div>')
    assert binding_issues(tmp_path, cms(lagy_lezer=page())) == []


def test_cms_field_without_dom_target(tmp_path):
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"></div>')
    found = binding_issues(tmp_path, cms(ai=page([{"key": "lead", "value": "x"}])))
    assert types(found) == ["cms_field_without_renderer_binding"]


def test_dom_field_without_cms_field(tmp_path):
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"><p data-cms-field="lead"></p></div>')
    found = binding_issues(tmp_path, cms(ai=page()))
    assert types(found) == ["renderer_binding_missing_field"]
    assert found[0]["severity"] == "warning"


def test_missing_required_title_field_is_error(tmp_path):
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"><h1 data-cms-field="title"></h1></div>')
    found = binding_issues(tmp_path, cms(ai=page()))
    assert found[0]["type"] == "renderer_binding_missing_field" and found[0]["severity"] == "error"


def test_empty_required_title_and_hero_title(tmp_path):
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"><h1 data-cms-field="title"></h1></div>')
    write_html(tmp_path, "preview.html", '<div data-cms-page="index"><h1 data-cms-field="hero_title"></h1></div>')
    data = cms(ai=page([{"key": "title", "value": ""}]),
               index=page([{"key": "hero_title", "value": "  "}], enabled=False))
    found = [x for x in binding_issues(tmp_path, data) if x["type"] == "required_binding_empty"]
    assert len(found) == 2 and all(x["severity"] == "error" for x in found)


def test_empty_optional_field_is_not_finding(tmp_path):
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"><p data-cms-field="lead"></p></div>')
    assert binding_issues(tmp_path, cms(ai=page([{"key": "lead", "value": ""}]))) == []


def test_supported_block_types_are_accepted(tmp_path):
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"></div>')
    blocks = [{"id": kind, "type": kind, "src": "https://example.test/x"} for kind in SUPPORTED_BLOCK_TYPES]
    assert "unsupported_block_type" not in types(binding_issues(tmp_path, cms(ai=page(blocks=blocks))))


def test_unsupported_block_type(tmp_path):
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"></div>')
    found = binding_issues(tmp_path, cms(ai=page(blocks=[{"id": "x", "type": "unknown"}])))
    assert types(found) == ["unsupported_block_type"]
    assert found[0]["category"] == "cms/rendering" and found[0]["severity"] == "error"


def test_blocks_without_mount_have_provable_missing_target(tmp_path):
    found = binding_issues(tmp_path, cms(ai=page(blocks=[{"type": "text", "text": "x"}])))
    assert {x["type"] for x in found} == {"cms_page_without_public_html", "block_target_missing"}


def test_unsupported_block_without_mount_is_reported_once(tmp_path):
    data = cms(ai=page(blocks=[{"id": "x", "type": "unknown"}]))
    direct = binding_issues(tmp_path, data)
    assert types(direct).count("unsupported_block_type") == 1
    integrated = detect_issues(data, CONFIG, project_root=tmp_path, detected_at=NOW)
    assert types(integrated).count("unsupported_block_type") == 1
    assert "malformed_block_type" not in types(integrated)


def test_hidden_unsupported_block_is_not_renderer_finding(tmp_path):
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"></div>')
    found = binding_issues(tmp_path, cms(ai=page(blocks=[
        {"type": "unknown", "visible": False},
    ])))
    assert "unsupported_block_type" not in types(found)


def test_hidden_url_only_video_is_not_renderer_mismatch(tmp_path):
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"></div>')
    found = binding_issues(tmp_path, cms(ai=page(blocks=[{
        "type": "video", "visible": False, "src": "",
        "url": "https://example.com/video",
    }])))
    assert "video_renderer_source_mismatch" not in types(found)


def test_visible_true_and_missing_unsupported_blocks_are_audited(tmp_path):
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"></div>')
    for block in ({"type": "unknown", "visible": True}, {"type": "unknown"}):
        found = binding_issues(tmp_path, cms(ai=page(blocks=[block])))
        assert "unsupported_block_type" in types(found)


def test_visible_true_and_missing_url_only_videos_are_audited(tmp_path):
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"></div>')
    for block in (
        {"type": "video", "visible": True, "src": "", "url": "https://example.com/video"},
        {"type": "video", "src": "", "url": "https://example.com/video"},
    ):
        found = binding_issues(tmp_path, cms(ai=page(blocks=[block])))
        assert "video_renderer_source_mismatch" in types(found)


def test_only_literal_false_is_hidden_from_renderer_audit(tmp_path):
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"></div>')
    for visible in (True, None, 0):
        found = binding_issues(tmp_path, cms(ai=page(blocks=[
            {"type": "unknown", "visible": visible},
        ])))
        assert "unsupported_block_type" in types(found)


def test_video_src_is_valid_for_renderer(tmp_path):
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"></div>')
    found = binding_issues(tmp_path, cms(ai=page(blocks=[{"type": "video", "src": "x.mp4"}])))
    assert "video_renderer_source_mismatch" not in types(found)


def test_video_url_only_is_renderer_mismatch(tmp_path):
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"></div>')
    found = binding_issues(tmp_path, cms(ai=page(blocks=[{"id": "v", "type": "video", "url": "https://example.test/v"}])))
    issue = next(x for x in found if x["type"] == "video_renderer_source_mismatch")
    assert issue["category"] == "rendering" and issue["severity"] == "warning"
    assert issue["evidence"]["renderer_expectation"] == "Nem üres block.src"


def test_disabled_page_is_not_itself_a_finding(tmp_path):
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"></div>')
    assert binding_issues(tmp_path, cms(ai=page(enabled=False))) == []


def test_empty_legal_and_booking_pages_are_valid(tmp_path):
    write_html(tmp_path, "adatkezeles.html", '<div data-cms-page="adatkezeles"></div>')
    write_html(tmp_path, "idopontfoglalas.html", '<div data-cms-page="idopontfoglalas"></div>')
    assert binding_issues(tmp_path, cms(adatkezeles=page(), idopontfoglalas=page())) == []


def test_fields_without_mount_produce_renderer_target_missing(tmp_path):
    write_html(tmp_path, "ai.html", '<h1 data-cms-field="title"></h1>')
    found = binding_issues(tmp_path, cms())
    assert types(found) == ["renderer_target_missing"]


def test_malformed_cms_remains_fail_closed(tmp_path):
    assert "malformed_cms_root" in types(detect_issues([], CONFIG, project_root=tmp_path, detected_at=NOW))
    assert "malformed_pages" in types(detect_issues({}, CONFIG, project_root=tmp_path, detected_at=NOW))


def test_binding_integration_requires_canonical_cms_source_when_source_is_declared(tmp_path):
    write_html(tmp_path, "ai.html", '<div data-cms-page="unknown"></div>')
    noncanonical = tmp_path / "fixture-pages.json"
    found = detect_issues(cms(), CONFIG, project_root=tmp_path, detected_at=NOW,
                          cms_source_path=noncanonical)
    assert "public_html_without_expected_cms_page" not in types(found)
    canonical = tmp_path / "assets" / "content" / "pages.json"
    found = detect_issues(cms(), CONFIG, project_root=tmp_path, detected_at=NOW,
                          cms_source_path=canonical)
    assert "public_html_without_expected_cms_page" in types(found)


def test_stable_id_deduplication_and_lifecycle(tmp_path):
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"><p data-cms-field="missing"></p><p data-cms-field="missing"></p></div>')
    first = binding_issues(tmp_path, cms(ai=page()))
    second = binding_issues(tmp_path, cms(ai=page()))
    assert len(first) == 1 and first[0]["issue_id"] == second[0]["issue_id"]
    old = copy.deepcopy(first[0]); old["status"] = "resolved"; old["resolved_at"] = "2026-08-19T00:00:00+00:00"
    reopened = merge_issue_lifecycle([old], second, now=NOW)[0]
    assert reopened["status"] == "open" and reopened["resolved_at"] is None


def test_secret_redaction(tmp_path):
    secret = "sk" + "-binding-secret-example-123456"
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"></div>')
    issue = binding_issues(tmp_path, cms(ai=page(blocks=[{"type": "video", "url": secret}])))[0]
    assert secret not in serialize_issue(issue) and "[REDACTED]" in serialize_issue(issue)


def test_each_html_is_read_and_parsed_once(tmp_path, monkeypatch):
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"><a href="#x">x</a></div>')
    original = Path.read_text
    reads = []
    def tracked(path, *args, **kwargs):
        reads.append(path.name)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", tracked)
    detect_issues(cms(ai=page()), CONFIG, project_root=tmp_path, detected_at=NOW)
    assert reads == ["ai.html"]


def test_unsafe_cms_values_never_become_html_paths(tmp_path, monkeypatch):
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"></div>')
    original = Path.is_file
    checked = []
    def tracked(path):
        checked.append(str(path))
        return original(path)
    monkeypatch.setattr(Path, "is_file", tracked)
    data = cms(ai=page([{"key": "../../secret", "value": "x"}]))
    binding_issues(tmp_path, data)
    assert all("secret" not in value and ".." not in value for value in checked)


def test_no_mutation(tmp_path):
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"></div>')
    data = cms(ai=page([{"key": "missing", "value": "x"}]))
    before_cms = copy.deepcopy(data); before_html = (tmp_path / "ai.html").read_bytes()
    binding_issues(tmp_path, data)
    assert data == before_cms and (tmp_path / "ai.html").read_bytes() == before_html


def test_no_network(tmp_path, monkeypatch):
    write_html(tmp_path, "ai.html", '<div data-cms-page="ai"></div>')
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    binding_issues(tmp_path, cms(ai=page()))


def test_no_ai_subprocess_or_network_imports():
    source = (SCRIPTS / "webmaster_audit.py").read_text(encoding="utf-8").lower()
    for forbidden in ("import subprocess", "import openai", "import requests", "import httpx",
                      "urlopen(", "create_connection("):
        assert forbidden not in source
