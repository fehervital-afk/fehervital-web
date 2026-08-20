import ast
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
    EXTERNAL_HTTP, EXTERNAL_HTTPS, FRAGMENT_ONLY, INTERNAL_HTML, MAILTO,
    OTHER_NON_HTML, PROTOCOL_RELATIVE_EXTERNAL, PUBLIC_HTML_ALLOWLIST, TEL,
    UNSAFE_LOCAL_PATH, build_html_link_index, classify_href,
    detect_internal_html_links, detect_issues,
)
from webmaster_models import merge_issue_lifecycle

NOW = "2026-08-20T08:00:00+00:00"


def write_public(root, files):
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def detect(root):
    return detect_internal_html_links(project_root=root, detected_at=NOW)


def test_valid_relative_internal_link(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="biorezonancia.html">B</a>',
                            "biorezonancia.html": "<p>ok</p>"})
    assert detect(tmp_path) == []


def test_valid_root_relative_internal_link(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="/kapcsolat.html">K</a>',
                            "kapcsolat.html": "<p>ok</p>"})
    assert detect(tmp_path) == []


def test_root_maps_to_index_html():
    result = classify_href("kapcsolat.html", "/")
    assert result.kind == INTERNAL_HTML and result.target == "index.html"


def test_index_aliases_normalize_to_index_html():
    assert classify_href("kapcsolat.html", "index.html").target == "index.html"
    assert classify_href("kapcsolat.html", "/index.html").target == "index.html"


def test_query_is_stripped_for_target_validation():
    result = classify_href("index.html", "/biorezonancia.html?x=1")
    assert result.kind == INTERNAL_HTML and result.target == "biorezonancia.html"


def test_fragment_is_extracted_without_broken_link_issue(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="biorezonancia.html#missing">B</a>',
                            "biorezonancia.html": "<p>no anchor</p>"})
    result = classify_href("index.html", "biorezonancia.html#missing")
    assert result.fragment == "missing"
    assert "broken_internal_link" not in [item["type"] for item in detect(tmp_path)]


def test_fragment_only_is_not_a_broken_link(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="#missing">X</a>'})
    assert classify_href("index.html", "#missing").kind == FRAGMENT_ONLY
    assert "broken_internal_link" not in [item["type"] for item in detect(tmp_path)]


def test_external_http_is_ignored(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="http://example.test/a">X</a>'})
    assert classify_href("index.html", "http://example.test/a").kind == EXTERNAL_HTTP
    assert detect(tmp_path) == []


def test_external_https_is_ignored(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="https://example.test/a">X</a>'})
    assert classify_href("index.html", "https://example.test/a").kind == EXTERNAL_HTTPS
    assert detect(tmp_path) == []


def test_protocol_relative_external_is_ignored():
    assert classify_href("index.html", "//example.test/a").kind == PROTOCOL_RELATIVE_EXTERNAL


def test_mailto_is_ignored():
    assert classify_href("index.html", "mailto:info@example.test").kind == MAILTO


def test_tel_is_ignored():
    assert classify_href("index.html", "tel:+361234567").kind == TEL


def test_broken_internal_html_is_reported(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="kapcsolat.html">K</a>'})
    issues = detect(tmp_path)
    assert len(issues) == 1 and issues[0]["type"] == "broken_internal_link"


def test_forward_slash_traversal_is_rejected():
    assert classify_href("index.html", "../secret.html").kind == UNSAFE_LOCAL_PATH


def test_backslash_traversal_is_rejected():
    assert classify_href("index.html", "..\\secret.html").kind == UNSAFE_LOCAL_PATH


def test_windows_drive_path_is_rejected():
    assert classify_href("index.html", "C:/secret.html").kind == UNSAFE_LOCAL_PATH


def test_unc_path_is_rejected():
    assert classify_href("index.html", "\\\\server\\secret.html").kind == UNSAFE_LOCAL_PATH


def test_sensitive_non_public_target_is_rejected_without_lookup(tmp_path, monkeypatch):
    write_public(tmp_path, {"index.html": '<a href="scripts/secret.html">X</a>'})
    original = Path.is_file
    looked_up = []
    def guarded(path):
        if "secret" in str(path):
            looked_up.append(path)
            raise AssertionError("sensitive lookup")
        return original(path)
    monkeypatch.setattr(Path, "is_file", guarded)
    issues = detect(tmp_path)
    assert issues[0]["type"] == "unsafe_internal_path"
    assert looked_up == []


def test_trailing_slash_is_not_converted_to_html():
    result = classify_href("index.html", "/service/")
    assert result.kind == OTHER_NON_HTML and result.target == "service"


def test_stable_issue_id_ignores_query_and_fragment_differences(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="missing.html?x=1#one">A</a>'})
    first = detect(tmp_path)[0]
    write_public(tmp_path, {"index.html": '<a href="missing.html?x=2#two">B</a>'})
    second = detect(tmp_path)[0]
    assert first["issue_id"] == second["issue_id"]


def test_duplicate_broken_target_is_deduplicated(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="missing.html?x=1">A</a><a href="missing.html#x">B</a>'})
    assert len(detect(tmp_path)) == 1


def test_original_href_is_retained_in_evidence(tmp_path):
    href = "missing.html?source=test#section"
    write_public(tmp_path, {"index.html": f'<a href="{href}">A</a>'})
    assert detect(tmp_path)[0]["evidence"]["original_href"] == href


def test_html_index_reads_each_existing_public_file_once(tmp_path, monkeypatch):
    write_public(tmp_path, {"index.html": '<a href="preview.html">P</a>', "preview.html": "ok"})
    original = Path.read_text
    reads = []
    def tracked(path, *args, **kwargs):
        reads.append(path.name)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", tracked)
    build_html_link_index(tmp_path)
    assert reads.count("index.html") == 1 and reads.count("preview.html") == 1


def test_no_network_even_for_external_links(tmp_path, monkeypatch):
    write_public(tmp_path, {"index.html": '<a href="https://example.test">X</a>'})
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    assert detect(tmp_path) == []


def test_no_network_subprocess_or_ai_sdk_imports():
    tree = ast.parse((SCRIPTS / "webmaster_audit.py").read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert imports.isdisjoint({"requests", "httpx", "socket", "subprocess", "openai", "google", "anthropic"})
    source = (SCRIPTS / "webmaster_audit.py").read_text(encoding="utf-8").lower()
    assert "urlopen" not in source and "gemini" not in source


def test_public_contract_matches_build_manifest():
    source = (SCRIPTS / "build_public.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    manifest = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PUBLIC_HTML" for t in node.targets):
            manifest = set(ast.literal_eval(node.value))
    assert manifest == set(PUBLIC_HTML_ALLOWLIST)


def test_no_mutation_of_project_inputs():
    protected = [ROOT / "assets/content/pages.json", ROOT / "assets/js/app.js",
                 ROOT / "scripts/automation_policy.py", ROOT / "scripts/executor_engine.py",
                 ROOT / "scripts/autopilot.py", ROOT / "scripts/build_public.py"]
    protected += sorted(ROOT.glob("*.html"))
    protected += sorted((ROOT / ".github/workflows").glob("*.yml"))
    protected += [p for p in sorted((ROOT / "assets/uploads").glob("**/*")) if p.is_file()]
    before = {path: path.read_bytes() for path in protected}
    detect_internal_html_links(project_root=ROOT, detected_at=NOW)
    assert {path: path.read_bytes() for path in protected} == before


def test_p1_1_lifecycle_compatibility(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="missing.html">X</a>'})
    current = detect(tmp_path)[0]
    old = copy.deepcopy(current)
    old["status"] = "planned"
    old["detected_at"] = "2026-08-19T08:00:00+00:00"
    merged = merge_issue_lifecycle([old], [current], now=NOW)
    assert merged[0]["status"] == "planned" and merged[0]["detected_at"] == old["detected_at"]


def test_p1_2_1_detector_regression(tmp_path):
    cms = {"pages": {"index": {
        "seo": {"title": "", "description": ""},
        "fields": [{"key": "title", "value": ""}],
        "blocks": [{"id": "image", "type": "image", "src": "assets/uploads/missing.png", "alt": ""}],
    }}}
    found = {item["type"] for item in detect_issues(cms, {}, project_root=tmp_path, detected_at=NOW)}
    assert {"seo_title", "seo_description", "required_content_empty", "missing_media",
            "alt_text", "booking_url"}.issubset(found)
