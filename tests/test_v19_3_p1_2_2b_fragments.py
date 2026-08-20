import ast
import copy
import socket
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from webmaster_audit import (
    build_html_link_index, classify_href, detect_internal_html_links,
    normalize_fragment,
)
from webmaster_models import merge_issue_lifecycle, serialize_issue

NOW = "2026-08-20T08:00:00+00:00"


def write_public(root, files):
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def detect(root):
    return detect_internal_html_links(project_root=root, detected_at=NOW)


def issue_types(items):
    return [item["type"] for item in items]


def test_valid_fragment_only(tmp_path):
    write_public(tmp_path, {"index.html": '<div id="mainNav"></div><a href="#mainNav">X</a>'})
    assert detect(tmp_path) == []


def test_missing_fragment_only(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="#missing">X</a>'})
    assert issue_types(detect(tmp_path)) == ["broken_internal_fragment"]


def test_valid_cross_page_fragment(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="kapcsolat.html#main">K</a>',
                            "kapcsolat.html": '<main id="main"></main>'})
    assert detect(tmp_path) == []


def test_missing_cross_page_fragment(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="kapcsolat.html#missing">K</a>',
                            "kapcsolat.html": "<main></main>"})
    assert issue_types(detect(tmp_path)) == ["broken_internal_fragment"]


def test_explicit_same_page_filename(tmp_path):
    write_public(tmp_path, {"index.html": '<div id="x"></div><a href="index.html#x">X</a>'})
    assert detect(tmp_path) == []


def test_root_alias_with_fragment(tmp_path):
    write_public(tmp_path, {"index.html": '<div id="x"></div>',
                            "kapcsolat.html": '<a href="/#x">X</a>'})
    assert detect(tmp_path) == []


def test_query_and_fragment_same_page(tmp_path):
    write_public(tmp_path, {"index.html": '<div id="mainNav"></div><a href="?page=1#mainNav">X</a>'})
    assert detect(tmp_path) == []


def test_query_difference_has_same_issue_id(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="kapcsolat.html?x=1#missing">X</a>',
                            "kapcsolat.html": "ok"})
    first = detect(tmp_path)[0]
    write_public(tmp_path, {"index.html": '<a href="kapcsolat.html?x=2#missing">X</a>',
                            "kapcsolat.html": "ok"})
    assert detect(tmp_path)[0]["issue_id"] == first["issue_id"]


def test_fragment_difference_has_different_issue_id(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="#one">X</a>'})
    first = detect(tmp_path)[0]
    write_public(tmp_path, {"index.html": '<a href="#two">X</a>'})
    assert detect(tmp_path)[0]["issue_id"] != first["issue_id"]


def test_fragment_is_case_sensitive(tmp_path):
    write_public(tmp_path, {"index.html": '<div id="Foo"></div><a href="#foo">X</a>'})
    assert issue_types(detect(tmp_path)) == ["broken_internal_fragment"]


def test_case_sensitive_fragments_have_distinct_findings_and_issue_ids(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="#Foo">A</a><a href="#foo">B</a>'})
    issues = detect(tmp_path)
    assert len(issues) == 2
    assert {item["evidence"]["fragment"] for item in issues} == {"Foo", "foo"}
    assert len({item["issue_id"] for item in issues}) == 2


def test_duplicate_case_sensitive_fragment_has_one_stable_issue_id(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="#Foo">A</a><a href="#Foo">B</a>'})
    first = detect(tmp_path)
    second = detect(tmp_path)
    assert len(first) == len(second) == 1
    assert first[0]["issue_id"] == second[0]["issue_id"]


def test_query_differences_do_not_change_case_sensitive_fragment_identity(tmp_path):
    write_public(tmp_path, {
        "index.html": (
            '<a href="kapcsolat.html?x=1#Foo">A</a>'
            '<a href="kapcsolat.html?x=2#Foo">B</a>'
        ),
        "kapcsolat.html": "ok",
    })
    assert len(detect(tmp_path)) == 1


def test_cross_page_case_sensitive_fragments_have_distinct_issue_ids(tmp_path):
    write_public(tmp_path, {
        "index.html": (
            '<a href="kapcsolat.html#Foo">A</a>'
            '<a href="kapcsolat.html#foo">B</a>'
        ),
        "kapcsolat.html": "ok",
    })
    issues = detect(tmp_path)
    assert len(issues) == 2
    assert len({item["issue_id"] for item in issues}) == 2


def test_unicode_anchor(tmp_path):
    write_public(tmp_path, {"index.html": '<div id="időpont"></div><a href="#időpont">X</a>'})
    assert detect(tmp_path) == []


def test_percent_encoded_unicode_fragment(tmp_path):
    write_public(tmp_path, {"index.html": '<div id="időpont"></div><a href="#id%C5%91pont">X</a>'})
    assert detect(tmp_path) == []


def test_fragment_decoded_exactly_once():
    assert normalize_fragment("%2520") == "%20"


def test_plus_is_not_decoded_as_space():
    assert normalize_fragment("a+b") == "a+b"


def test_malformed_utf8_and_percent_are_ignored(tmp_path):
    assert normalize_fragment("%FF") is None
    assert normalize_fragment("%ZZ") is None
    write_public(tmp_path, {"index.html": '<a href="#%FF">X</a><a href="#%ZZ">Y</a>'})
    assert detect(tmp_path) == []


def test_hash_only_is_ignored(tmp_path):
    write_public(tmp_path, {"index.html": "ok", "kapcsolat.html": '<a href="#">X</a>'})
    assert detect(tmp_path) == []


def test_empty_href_is_ignored(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="">X</a>'})
    assert detect(tmp_path) == []


def test_external_fragments_are_ignored(tmp_path):
    write_public(tmp_path, {"index.html": (
        '<a href="http://example.test/#x">A</a>'
        '<a href="https://example.test/#x">B</a>'
        '<a href="//example.test/#x">C</a>'
    )})
    assert detect(tmp_path) == []


def test_mailto_tel_and_other_fragments_are_ignored(tmp_path):
    write_public(tmp_path, {"index.html": (
        '<a href="mailto:test@example.test#x">A</a>'
        '<a href="tel:+36123#x">B</a>'
        '<a href="javascript:void(0)#x">C</a>'
    )})
    assert detect(tmp_path) == []


def test_unsafe_target_with_fragment_only_creates_unsafe_issue(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="../secret.html#x">X</a>'})
    assert issue_types(detect(tmp_path)) == ["unsafe_internal_path"]


def test_broken_target_with_fragment_only_creates_broken_link(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="missing.html#x">X</a>'})
    assert issue_types(detect(tmp_path)) == ["broken_internal_link"]


def test_fragment_and_query_never_enter_filesystem_target(tmp_path, monkeypatch):
    write_public(tmp_path, {"index.html": '<a href="kapcsolat.html?q=secret#fragment">X</a>',
                            "kapcsolat.html": '<div id="fragment"></div>'})
    original = Path.is_file
    checked = []
    def tracked(path):
        checked.append(str(path))
        return original(path)
    monkeypatch.setattr(Path, "is_file", tracked)
    assert detect(tmp_path) == []
    assert all("?" not in path and "#" not in path and "secret" not in path for path in checked)


def test_each_html_is_read_once(tmp_path, monkeypatch):
    write_public(tmp_path, {"index.html": '<a href="kapcsolat.html#x">X</a>',
                            "kapcsolat.html": '<div id="x"></div>'})
    original = Path.read_text
    reads = []
    def tracked(path, *args, **kwargs):
        reads.append(path.name)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", tracked)
    detect(tmp_path)
    assert reads.count("index.html") == 1 and reads.count("kapcsolat.html") == 1


def test_duplicate_fragment_is_deduplicated_and_first_href_retained(tmp_path):
    write_public(tmp_path, {"index.html": (
        '<a href="kapcsolat.html?first=1#missing">A</a>'
        '<a href="kapcsolat.html?second=2#missing">B</a>'
    ), "kapcsolat.html": "ok"})
    issues = detect(tmp_path)
    assert len(issues) == 1
    assert issues[0]["evidence"]["original_href"] == "kapcsolat.html?first=1#missing"


def test_id_and_legacy_name_anchors_are_collected(tmp_path):
    write_public(tmp_path, {"index.html": '<div id="one"></div><a name="two"></a>'})
    document = build_html_link_index(tmp_path)["index.html"]
    assert document.anchors == {"one", "two"}


def test_duplicate_id_and_id_name_collision_are_valid_anchors(tmp_path):
    write_public(tmp_path, {"index.html": (
        '<div id="same"></div><span id="same"></span><a name="same"></a>'
        '<a href="#same">X</a>'
    )})
    document = build_html_link_index(tmp_path)["index.html"]
    assert document.anchor_counts["same"] == 3
    assert detect(tmp_path) == []


def test_fragment_issue_evidence(tmp_path):
    href = "kapcsolat.html?q=1#missing"
    write_public(tmp_path, {"index.html": f'<nav><a href="{href}">X</a></nav>',
                            "kapcsolat.html": "ok"})
    issue = detect(tmp_path)[0]
    assert issue["type"] == "broken_internal_fragment"
    assert issue["evidence"] == {
        "source": "index.html", "original_href": href,
        "normalized_target": "kapcsolat.html", "fragment": "missing",
        "context": "nav", "expected": "Létező id vagy legacy a[name] anchor.",
    }
    assert issue["policy_risk"] == "UNKNOWN"
    assert issue["suggested_action"]["action"] == "review_link"


def test_lifecycle_compatibility_and_resolved_reopen(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="#missing">X</a>'})
    current = detect(tmp_path)[0]
    planned = copy.deepcopy(current)
    planned["status"] = "planned"
    planned["detected_at"] = "2026-08-19T08:00:00+00:00"
    assert merge_issue_lifecycle([planned], [current], now=NOW)[0]["status"] == "planned"
    resolved = copy.deepcopy(planned)
    resolved["status"] = "resolved"
    resolved["resolved_at"] = "2026-08-19T12:00:00+00:00"
    reopened = merge_issue_lifecycle([resolved], [current], now=NOW)[0]
    assert reopened["status"] == "open" and reopened["resolved_at"] is None


def test_case_sensitive_fragment_lifecycle_is_stable_and_reopens(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="#Foo">X</a>'})
    first = detect(tmp_path)[0]
    previous = copy.deepcopy(first)
    previous["detected_at"] = "2026-08-19T08:00:00+00:00"
    merged = merge_issue_lifecycle([previous], [first], now=NOW)[0]
    assert merged["issue_id"] == first["issue_id"]
    assert merged["detected_at"] == "2026-08-19T08:00:00+00:00"
    assert merged["last_seen_at"] == NOW

    resolved = copy.deepcopy(merged)
    resolved["status"] = "resolved"
    resolved["resolved_at"] = "2026-08-19T12:00:00+00:00"
    reopened = merge_issue_lifecycle([resolved], [first], now=NOW)[0]
    assert reopened["issue_id"] == first["issue_id"]
    assert reopened["status"] == "open"
    assert reopened["resolved_at"] is None


def test_resolved_uppercase_fragment_does_not_merge_with_new_lowercase_fragment(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="#Foo">X</a>'})
    upper = detect(tmp_path)[0]
    upper["status"] = "resolved"
    upper["resolved_at"] = "2026-08-19T12:00:00+00:00"

    write_public(tmp_path, {"index.html": '<a href="#foo">X</a>'})
    lower = detect(tmp_path)[0]
    merged = merge_issue_lifecycle([upper], [lower], now=NOW)
    assert len(merged) == 2
    by_fragment = {item["evidence"]["fragment"]: item for item in merged}
    assert by_fragment["Foo"]["status"] == "resolved"
    assert by_fragment["foo"]["status"] == "open"
    assert by_fragment["Foo"]["issue_id"] != by_fragment["foo"]["issue_id"]


def test_secret_redaction(tmp_path):
    secret = "sk" + "-example-fragment-secret-123456"
    write_public(tmp_path, {"index.html": f'<a href="#api_key={secret}">X</a>'})
    serialized = serialize_issue(detect(tmp_path)[0])
    assert secret not in serialized and "[REDACTED]" in serialized


def test_no_mutation(tmp_path):
    write_public(tmp_path, {"index.html": '<a href="#missing">X</a>'})
    before = (tmp_path / "index.html").read_bytes()
    detect(tmp_path)
    assert (tmp_path / "index.html").read_bytes() == before


def test_no_network(tmp_path, monkeypatch):
    write_public(tmp_path, {"index.html": '<a href="https://example.test/#x">X</a>'})
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    assert detect(tmp_path) == []


def test_no_ai_or_subprocess_imports():
    source = (SCRIPTS / "webmaster_audit.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert imports.isdisjoint({"requests", "httpx", "socket", "subprocess",
                               "openai", "google", "anthropic"})
    lowered = source.lower()
    assert "urlopen" not in lowered and "gemini" not in lowered
