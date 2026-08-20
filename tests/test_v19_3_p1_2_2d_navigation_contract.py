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
    HTMLDocumentIndex, IndexedLink, REQUIRED_PUBLIC_HTML_CONTRACT, _LinkParser,
    _normalized_label,
    STANDARD_CMS_HTML_CONTRACT, STANDARD_FOOTER_CONTRACT,
    STANDARD_NAVIGATION_CONTRACT, build_html_link_index, detect_site_structure,
)
from webmaster_models import merge_issue_lifecycle, serialize_issue

NOW = "2026-08-20T08:00:00+00:00"


def link(source, href, label, context, position):
    return IndexedLink(source=source, href=href, context=context, label=label, position=position)


def document(source, *, nav=None, footer=None, mounts=()):
    links = []
    for position, (label, href) in enumerate(nav or [], start=1):
        links.append(link(source, href, label, "nav", position))
    for position, (label, href) in enumerate(footer or [], start=1):
        links.append(link(source, href, label, "footer", position))
    return HTMLDocumentIndex(source, links, set(), {}, tuple(mounts), ())


def valid_documents():
    docs = {"index.html": document("index.html")}
    for source in STANDARD_CMS_HTML_CONTRACT:
        docs[source] = document(source, nav=STANDARD_NAVIGATION_CONTRACT,
                                footer=STANDARD_FOOTER_CONTRACT, mounts=(source,))
    return docs


def audit(documents, public_contract=REQUIRED_PUBLIC_HTML_CONTRACT):
    return detect_site_structure(project_root=ROOT, detected_at=NOW, documents=documents,
                                 public_contract=frozenset(public_contract))


def types(items):
    return [item["type"] for item in items]


def parse_links(html):
    parser = _LinkParser("sample.html")
    parser.feed(html)
    parser.close()
    return parser.links


def test_parser_navigation_positions_are_one_based():
    html = "<nav>" + "".join(
        f'<a href="{href}">{label}</a>' for label, href in STANDARD_NAVIGATION_CONTRACT
    ) + "</nav>"
    links = parse_links(html)
    assert [item.position for item in links] == [1, 2, 3, 4, 5, 6, 7]
    assert [_normalized_label(item.label) for item in links] == [
        "Főoldal", "Biorezonancia", "HarmonyScan", "Recepciós AI",
        "Fehérvitál AI", "Kapcsolat", "Időpontfoglalás",
    ]


def test_parser_footer_positions_are_one_based():
    links = parse_links(
        '<footer><a href="kapcsolat.html">Kapcsolat</a>'
        '<a href="adatkezeles.html">Adatkezelés</a></footer>'
    )
    assert [(item.label, item.position) for item in links] == [
        ("Kapcsolat", 1), ("Adatkezelés", 2),
    ]


def test_parser_content_positions_are_one_based():
    links = parse_links('<main><a href="a">Első</a><a href="b">Második</a></main>')
    assert [(item.context, item.position) for item in links] == [("content", 1), ("content", 2)]


def test_parser_context_positions_are_independent():
    links = parse_links(
        '<nav><a href="n1">N1</a><a href="n2">N2</a></nav>'
        '<main><a href="c1">C1</a></main>'
        '<footer><a href="f1">F1</a><a href="f2">F2</a></footer>'
    )
    assert [(item.context, item.position) for item in links] == [
        ("nav", 1), ("nav", 2), ("content", 1), ("footer", 1), ("footer", 2),
    ]


def test_nested_label_and_multiline_whitespace_regression():
    links = parse_links(
        '<nav><a href="x.html"><span>Kapcsolat</span></a>'
        '<a href="y.html">\n  Adatkezelés\n</a></nav>'
    )
    assert links[0].label == "Kapcsolat"
    assert _normalized_label(links[1].label) == "Adatkezelés"


def test_required_page_contract_is_explicit():
    assert REQUIRED_PUBLIC_HTML_CONTRACT == {
        "index.html", "preview.html", "biorezonancia.html", "harmonyscan.html",
        "ai.html", "kapcsolat.html", "adatkezeles.html", "idopontfoglalas.html",
        "recepcios-ai.html", "egeszsegpont.html", "termekek.html",
        "oxigenkoncentrator.html", "lagy-lezer.html", "vorosfenyu-hajapolo-sisak.html",
    }


def test_required_pages_present():
    assert audit(valid_documents()) == []


def test_required_page_missing():
    docs = valid_documents(); del docs["ai.html"]
    found = audit(docs)
    assert types(found).count("required_public_page_missing") == 1
    assert found[0]["evidence"]["filename"] == "ai.html"


def test_required_page_not_in_build_contract():
    contract = REQUIRED_PUBLIC_HTML_CONTRACT - {"ai.html"}
    found = audit(valid_documents(), contract)
    assert types(found) == ["required_page_not_in_build_contract"]


def test_optional_non_contract_page_is_not_finding():
    docs = valid_documents(); docs["optional.html"] = document("optional.html")
    assert audit(docs) == []


def test_static_index_has_no_standard_nav_or_footer_findings():
    found = audit(valid_documents())
    assert not any(item["page"] == "index.html" and item["category"] in {"navigation", "footer"}
                   for item in found)


def test_disabled_cms_state_is_not_part_of_page_contract_decision():
    assert "enabled" not in detect_site_structure.__code__.co_names
    assert audit(valid_documents()) == []


def test_complete_navigation():
    assert "required_navigation_link_missing" not in types(audit(valid_documents()))


def test_missing_navigation_item():
    docs = valid_documents(); docs["ai.html"] = document(
        "ai.html", nav=STANDARD_NAVIGATION_CONTRACT[:-1], footer=STANDARD_FOOTER_CONTRACT)
    assert "required_navigation_link_missing" in types(audit(docs))


def test_unexpected_navigation_item():
    docs = valid_documents(); docs["ai.html"] = document(
        "ai.html", nav=STANDARD_NAVIGATION_CONTRACT + (("Extra", "extra.html"),),
        footer=STANDARD_FOOTER_CONTRACT)
    assert "unexpected_navigation_link" in types(audit(docs))


def test_navigation_label_mismatch_is_case_sensitive():
    nav = list(STANDARD_NAVIGATION_CONTRACT); nav[0] = ("főoldal", "preview.html")
    docs = valid_documents(); docs["ai.html"] = document("ai.html", nav=nav, footer=STANDARD_FOOTER_CONTRACT)
    assert "navigation_label_mismatch" in types(audit(docs))


def test_navigation_unicode_label_mismatch():
    nav = list(STANDARD_NAVIGATION_CONTRACT); nav[3] = ("Recepcios AI", "recepcios-ai.html")
    docs = valid_documents(); docs["ai.html"] = document("ai.html", nav=nav, footer=STANDARD_FOOTER_CONTRACT)
    assert "navigation_label_mismatch" in types(audit(docs))


def test_navigation_target_mismatch():
    nav = list(STANDARD_NAVIGATION_CONTRACT); nav[0] = ("Főoldal", "ai.html")
    docs = valid_documents(); docs["ai.html"] = document("ai.html", nav=nav, footer=STANDARD_FOOTER_CONTRACT)
    assert "navigation_target_mismatch" in types(audit(docs))


def test_navigation_order_mismatch():
    nav = list(STANDARD_NAVIGATION_CONTRACT); nav[0], nav[1] = nav[1], nav[0]
    docs = valid_documents(); docs["ai.html"] = document("ai.html", nav=nav, footer=STANDARD_FOOTER_CONTRACT)
    order = [x for x in audit(docs) if x["type"] == "navigation_target_mismatch"]
    assert len(order) == 1 and order[0]["evidence"].get("actual_order")


def test_navigation_label_whitespace_is_normalized():
    nav = list(STANDARD_NAVIGATION_CONTRACT); nav[0] = ("  Főoldal\n ", "preview.html")
    docs = valid_documents(); docs["ai.html"] = document("ai.html", nav=nav, footer=STANDARD_FOOTER_CONTRACT)
    assert "navigation_label_mismatch" not in types(audit(docs))


def test_external_booking_url_is_exact_string_contract():
    nav = list(STANDARD_NAVIGATION_CONTRACT); nav[-1] = (
        "Időpontfoglalás", "https://recepciosai.hu/b/fehervital-egeszsegpont/")
    docs = valid_documents(); docs["ai.html"] = document("ai.html", nav=nav, footer=STANDARD_FOOTER_CONTRACT)
    mismatch = next(x for x in audit(docs) if x["type"] == "navigation_target_mismatch")
    assert mismatch["evidence"]["expected_position"] == 7


def test_external_booking_never_uses_network(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    assert audit(valid_documents()) == []


def test_brand_link_outside_nav_is_not_item():
    docs = valid_documents(); doc = docs["ai.html"]
    doc.links.append(link("ai.html", "preview.html", "Fehérvitál", "content", 0))
    assert audit(docs) == []


def test_active_state_is_not_required():
    assert audit(valid_documents()) == []


def test_complete_footer():
    assert "required_footer_link_missing" not in types(audit(valid_documents()))


def test_missing_contact_footer_link():
    docs = valid_documents(); docs["ai.html"] = document(
        "ai.html", nav=STANDARD_NAVIGATION_CONTRACT, footer=STANDARD_FOOTER_CONTRACT[1:])
    assert "required_footer_link_missing" in types(audit(docs))


def test_missing_privacy_footer_link():
    docs = valid_documents(); docs["ai.html"] = document(
        "ai.html", nav=STANDARD_NAVIGATION_CONTRACT, footer=STANDARD_FOOTER_CONTRACT[:1])
    assert "required_footer_link_missing" in types(audit(docs))


def test_footer_target_mismatch():
    footer = list(STANDARD_FOOTER_CONTRACT); footer[0] = ("Kapcsolat", "ai.html")
    docs = valid_documents(); docs["ai.html"] = document("ai.html", nav=STANDARD_NAVIGATION_CONTRACT, footer=footer)
    assert "footer_target_mismatch" in types(audit(docs))


def test_footer_label_mismatch():
    footer = list(STANDARD_FOOTER_CONTRACT); footer[0] = ("Elérhetőség", "kapcsolat.html")
    docs = valid_documents(); docs["ai.html"] = document("ai.html", nav=STANDARD_NAVIGATION_CONTRACT, footer=footer)
    assert "footer_label_mismatch" in types(audit(docs))


def test_extra_footer_link_is_not_finding():
    footer = STANDARD_FOOTER_CONTRACT + (("Extra", "extra.html"),)
    docs = valid_documents(); docs["ai.html"] = document("ai.html", nav=STANDARD_NAVIGATION_CONTRACT, footer=footer)
    assert audit(docs) == []


def test_same_document_duplicate_cms_mount():
    docs = valid_documents(); docs["ai.html"].cms_pages = ("ai", "ai")
    found = audit(docs)
    assert types(found).count("duplicate_cms_page_mount") == 1


def test_cross_document_duplicate_cms_mount_is_not_finding():
    docs = valid_documents(); docs["ai.html"].cms_pages = ("shared",); docs["preview.html"].cms_pages = ("shared",)
    assert "duplicate_cms_page_mount" not in types(audit(docs))


def test_stable_id_deduplication_and_reopen():
    docs = valid_documents(); docs["ai.html"].cms_pages = ("ai", "ai", "ai")
    first = audit(docs); second = audit(docs)
    duplicate = [x for x in first if x["type"] == "duplicate_cms_page_mount"]
    assert len(duplicate) == 1
    current = duplicate[0]; again = next(x for x in second if x["type"] == current["type"])
    assert current["issue_id"] == again["issue_id"]
    old = copy.deepcopy(current); old["status"] = "resolved"; old["resolved_at"] = "2026-08-19T00:00:00+00:00"
    reopened = merge_issue_lifecycle([old], [again], now=NOW)[0]
    assert reopened["status"] == "open" and reopened["resolved_at"] is None


def test_secret_redaction():
    secret = "sk" + "-navigation-secret-example-123456"
    docs = valid_documents(); docs["ai.html"].links.append(link("ai.html", secret, secret, "nav", 8))
    issue = next(x for x in audit(docs) if x["type"] == "unexpected_navigation_link")
    assert secret not in serialize_issue(issue) and "[REDACTED]" in serialize_issue(issue)


def test_html_is_read_and_parsed_once(tmp_path, monkeypatch):
    (tmp_path / "ai.html").write_text('<nav><a href="preview.html">Főoldal</a></nav>', encoding="utf-8")
    original = Path.read_text; reads = []
    def tracked(path, *args, **kwargs):
        reads.append(path.name); return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", tracked)
    docs = build_html_link_index(tmp_path)
    detect_site_structure(project_root=tmp_path, detected_at=NOW, documents=docs)
    assert reads == ["ai.html"]


def test_no_mutation():
    docs = valid_documents(); before = copy.deepcopy(docs)
    audit(docs)
    assert docs == before


def test_no_ai_network_or_subprocess_in_audit_engine():
    source = (SCRIPTS / "webmaster_audit.py").read_text(encoding="utf-8").lower()
    for forbidden in ("import subprocess", "import openai", "import requests", "import socket",
                      "import anthropic", "gemini", "urlopen(", "create_connection("):
        assert forbidden not in source
