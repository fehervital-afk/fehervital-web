#!/usr/bin/env python3
"""Deterministic, local-only website audit detectors.

The engine accepts already loaded CMS/config data and may only inspect media
below the fixed project root. It never writes files, uses the network, calls an
AI service, evaluates policy, or executes a suggested action.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, unquote_to_bytes, urlsplit

from webmaster_models import create_issue

SUPPORTED_BLOCK_TYPES = {
    "text", "image", "video", "iconbox", "testimonial", "price",
    "buttons", "divider", "cta", "faq",
}
# Audit-only allowlist. Only fields proven to bind to an H1 in the current
# renderer may appear here; unknown or optional empty fields must not produce a
# required_content_empty issue.
REQUIRED_CONTENT_FIELD_ALLOWLIST = {"title", "hero_title"}
SEVERITY_MAP = {"low": "info", "medium": "warning", "high": "error"}
EXTERNAL_URL = re.compile(r"^https?://", re.IGNORECASE)

# Explicit audited contract matching build_public.PUBLIC_HTML. Keeping this
# local avoids coupling the read-only detector to the mutating build module.
PUBLIC_HTML_ALLOWLIST = frozenset({
    "index.html", "preview.html", "biorezonancia.html", "harmonyscan.html",
    "ai.html", "kapcsolat.html", "adatkezeles.html", "idopontfoglalas.html",
    "recepcios-ai.html", "egeszsegpont.html", "termekek.html",
    "oxigenkoncentrator.html", "lagy-lezer.html",
    "vorosfenyu-hajapolo-sisak.html",
})

INTERNAL_HTML = "INTERNAL_HTML"
EXTERNAL_HTTP = "EXTERNAL_HTTP"
EXTERNAL_HTTPS = "EXTERNAL_HTTPS"
PROTOCOL_RELATIVE_EXTERNAL = "PROTOCOL_RELATIVE_EXTERNAL"
MAILTO = "MAILTO"
TEL = "TEL"
FRAGMENT_ONLY = "FRAGMENT_ONLY"
UNSAFE_LOCAL_PATH = "UNSAFE_LOCAL_PATH"
OTHER_NON_HTML = "OTHER/NON_HTML"

SENSITIVE_LOCAL_PREFIXES = {
    ".git", ".github", ".env", "_local_admin", "scripts", "tests", "dist",
    "assets/content",
}


@dataclass(frozen=True)
class IndexedLink:
    source: str
    href: str
    context: str


@dataclass
class HTMLDocumentIndex:
    source: str
    links: list[IndexedLink]
    anchors: set[str]
    anchor_counts: dict[str, int]


@dataclass(frozen=True)
class ClassifiedLink:
    kind: str
    target: str | None = None
    fragment: str | None = None
    reason: str = ""


class _LinkParser(HTMLParser):
    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.source = source
        self.links: list[IndexedLink] = []
        self.anchors: set[str] = set()
        self.anchor_counts: dict[str, int] = {}
        self._contexts: list[str] = []

    def _add_anchor(self, value: str | None) -> None:
        if value is None or value == "":
            return
        self.anchors.add(value)
        self.anchor_counts[value] = self.anchor_counts.get(value, 0) + 1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        attributes = {name.lower(): value for name, value in attrs if value is not None}
        if lowered in {"nav", "footer"}:
            self._contexts.append(lowered)
        self._add_anchor(attributes.get("id"))
        if lowered == "a":
            self._add_anchor(attributes.get("name"))
            href = attributes.get("href")
            if href is not None:
                self.links.append(IndexedLink(
                    source=self.source, href=href,
                    context=self._contexts[-1] if self._contexts else "content",
                ))

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"nav", "footer"} and self._contexts:
            self._contexts.pop()


def build_html_link_index(project_root: Path) -> dict[str, HTMLDocumentIndex]:
    """Parse each existing allowlisted source HTML exactly once."""
    root = project_root.resolve()
    index: dict[str, HTMLDocumentIndex] = {}
    for relative in sorted(PUBLIC_HTML_ALLOWLIST):
        source = root / relative
        if not source.is_file():
            continue
        parser = _LinkParser(relative)
        parser.feed(source.read_text(encoding="utf-8", errors="replace"))
        parser.close()
        index[relative] = HTMLDocumentIndex(
            source=relative, links=parser.links, anchors=parser.anchors,
            anchor_counts=parser.anchor_counts,
        )
    return index


def normalize_fragment(raw_fragment: str) -> str | None:
    """Decode a non-empty URL fragment exactly once using strict UTF-8."""
    if raw_fragment == "" or re.search(r"%(?![0-9A-Fa-f]{2})", raw_fragment):
        return None
    try:
        return unquote_to_bytes(raw_fragment).decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None


def classify_href(source: str, href: str) -> ClassifiedLink:
    """Classify and normalize an href without touching the filesystem."""
    raw = str(href or "").strip()
    if not raw:
        return ClassifiedLink(OTHER_NON_HTML)
    if raw == "#":
        return ClassifiedLink(FRAGMENT_ONLY)
    if raw.startswith("\\\\"):
        return ClassifiedLink(UNSAFE_LOCAL_PATH, reason="UNC paths are forbidden.")
    if re.match(r"^[A-Za-z]:[\\/]", raw):
        return ClassifiedLink(UNSAFE_LOCAL_PATH, reason="Drive paths are forbidden.")
    if raw.startswith("//"):
        return ClassifiedLink(PROTOCOL_RELATIVE_EXTERNAL)

    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    if scheme == "http":
        return ClassifiedLink(EXTERNAL_HTTP, fragment=normalize_fragment(parsed.fragment))
    if scheme == "https":
        return ClassifiedLink(EXTERNAL_HTTPS, fragment=normalize_fragment(parsed.fragment))
    if scheme == "mailto":
        return ClassifiedLink(MAILTO)
    if scheme == "tel":
        return ClassifiedLink(TEL)
    if scheme:
        return ClassifiedLink(OTHER_NON_HTML)
    if not parsed.path and parsed.fragment:
        return ClassifiedLink(FRAGMENT_ONLY, fragment=normalize_fragment(parsed.fragment))

    normalized_path = unquote(parsed.path).replace("\\", "/")
    parts = PurePosixPath(normalized_path).parts
    if ".." in parts:
        return ClassifiedLink(UNSAFE_LOCAL_PATH, reason="Path traversal is forbidden.")
    relative_parts = tuple(part for part in parts if part not in {"/", ""})
    lowered = "/".join(relative_parts).lower()
    if any(lowered == prefix or lowered.startswith(prefix + "/")
           for prefix in SENSITIVE_LOCAL_PREFIXES):
        return ClassifiedLink(UNSAFE_LOCAL_PATH, reason="Sensitive local target is forbidden.")
    if any(part.startswith(".") for part in relative_parts):
        return ClassifiedLink(UNSAFE_LOCAL_PATH, reason="Hidden local target is forbidden.")

    if normalized_path in {"", "/"}:
        target = "index.html"
    else:
        source_parent = PurePosixPath(source).parent
        candidate = PurePosixPath(*relative_parts) if normalized_path.startswith("/") else source_parent.joinpath(*relative_parts)
        target = candidate.as_posix()
        if target.startswith("./"):
            target = target[2:]
    if not target.lower().endswith(".html"):
        return ClassifiedLink(OTHER_NON_HTML, target=target, fragment=normalize_fragment(parsed.fragment))
    return ClassifiedLink(INTERNAL_HTML, target=target, fragment=normalize_fragment(parsed.fragment))


def detect_internal_html_links(*, project_root: Path, detected_at: str) -> list[dict[str, Any]]:
    """Return deduplicated P1.1 issues for unsafe or broken local HTML links."""
    root = project_root.resolve()
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    documents = build_html_link_index(root)
    for source, document in documents.items():
        for link in document.links:
            classified = classify_href(source, link.href)
            if classified.kind == UNSAFE_LOCAL_PATH:
                issue_type = "unsafe_internal_path"
                normalized_target = unquote(urlsplit(link.href.replace("\\", "/")).path)
                dedupe_key = (source, normalized_target, issue_type)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                findings.append(create_issue(
                    page=source, category="links", issue_type=issue_type, severity="error",
                    title="Nem biztonságos belső útvonal",
                    description="A hivatkozás tiltott vagy érzékeny helyi útvonalra mutat.",
                    evidence={"source": source, "original_href": link.href,
                              "normalized_target": normalized_target,
                              "context": link.context, "reason": classified.reason},
                    detected_at=detected_at, suggested_action={
                        "action": "review_link", "target": source,
                        "reason": "A tiltott helyi hivatkozást embernek kell felülvizsgálnia.",
                    }, policy_risk="UNKNOWN", target=normalized_target or "unsafe-local-path",
                    legacy_severity="high",
                ))
                continue
            if classified.kind == FRAGMENT_ONLY:
                target = source
                target_document = document
            elif classified.kind == INTERNAL_HTML and classified.target:
                target = classified.target
                dedupe_key = (source, target, "broken_internal_link")
                if dedupe_key in seen:
                    continue
                if target not in PUBLIC_HTML_ALLOWLIST or not (root / target).is_file():
                    seen.add(dedupe_key)
                    findings.append(create_issue(
                        page=source, category="links", issue_type="broken_internal_link",
                        severity="warning", title="Hibás belső HTML hivatkozás",
                        description=f"A belső HTML cél nem publikus vagy nem létezik: {target}",
                        evidence={"source": source, "original_href": link.href,
                                  "normalized_target": target, "fragment": classified.fragment,
                                  "context": link.context, "expected": "Létező, allowlisted publikus HTML."},
                        detected_at=detected_at, suggested_action={
                            "action": "review_link", "target": source,
                            "reason": "A hibás belső hivatkozást embernek kell felülvizsgálnia.",
                        }, policy_risk="UNKNOWN", target=target, legacy_severity="medium",
                    ))
                    continue
                target_document = documents.get(target)
                if target_document is None:
                    continue
            else:
                continue

            fragment = classified.fragment
            if fragment is None:
                continue
            fragment_key = (source, f"{target}#{fragment}", "broken_internal_fragment")
            if fragment_key in seen or fragment in target_document.anchors:
                continue
            seen.add(fragment_key)
            findings.append(create_issue(
                page=source, category="links", issue_type="broken_internal_fragment",
                severity="warning", title="Hiányzó belső hivatkozási pont",
                description=f"A céloldalon nem található a hivatkozott fragment: {target}#{fragment}",
                evidence={"source": source, "original_href": link.href,
                          "normalized_target": target, "fragment": fragment,
                          "context": link.context, "expected": "Létező id vagy legacy a[name] anchor."},
                detected_at=detected_at, suggested_action={
                    "action": "review_link", "target": source,
                    "reason": "A hiányzó fragmentet embernek kell felülvizsgálnia.",
                }, policy_risk="UNKNOWN", target=target, legacy_severity="medium",
                case_sensitive_identity=fragment,
            ))
    return findings


def _block_target(block: dict[str, Any], index: int) -> str:
    block_id = str(block.get("id") or "").strip()
    if block_id:
        return f"blocks.id.{block_id}"
    block_type = str(block.get("type") or "unknown").strip().lower()
    source = str(block.get("src") or block.get("url") or "").strip().replace("\\", "/")
    if source:
        return f"blocks.{block_type}.{source}"
    return f"blocks.{block_type}.{index}"


def _safe_upload_path(project_root: Path, value: str) -> tuple[Path | None, str | None]:
    normalized = value.strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or re.match(r"^[A-Za-z]:", normalized):
        return None, "absolute_or_empty"
    if ".." in path.parts or path.parts[:2] != ("assets", "uploads"):
        return None, "outside_uploads"
    root = project_root.resolve()
    candidate = (root / Path(*path.parts)).resolve()
    try:
        candidate.relative_to(root / "assets" / "uploads")
    except ValueError:
        return None, "outside_uploads"
    return candidate, None


def detect_issues(cms: Any, config: Any, *, project_root: Path,
                  detected_at: str) -> list[dict[str, Any]]:
    """Return P1.1 issues without mutating inputs or project content."""
    detected: list[dict[str, Any]] = []

    def add(*, legacy_severity: str, page: str, issue_type: str, category: str,
            title: str, description: str, evidence: dict[str, Any], target: str,
            suggested_action: dict[str, Any] | None = None) -> None:
        detected.append(create_issue(
            page=page, category=category, issue_type=issue_type,
            severity=SEVERITY_MAP[legacy_severity], title=title,
            description=description, evidence=evidence, detected_at=detected_at,
            suggested_action=suggested_action, policy_risk="UNKNOWN",
            target=target, legacy_severity=legacy_severity,
        ))

    if not isinstance(cms, dict):
        add(legacy_severity="high", page="site", issue_type="malformed_cms_root",
            category="technical", title="Hibás CMS gyökérstruktúra",
            description="A CMS gyökére nem objektum.", target="cms.root",
            evidence={"target": "cms.root", "expected": "object", "actual_type": type(cms).__name__})
        return detected

    pages = cms.get("pages")
    if not isinstance(pages, dict):
        add(legacy_severity="high", page="site", issue_type="malformed_pages",
            category="technical", title="Hibás pages struktúra",
            description="A CMS pages értéke nem objektum.", target="cms.pages",
            evidence={"target": "cms.pages", "expected": "object", "actual_type": type(pages).__name__})
        return detected

    for raw_slug, page_data in pages.items():
        slug = str(raw_slug)
        if not isinstance(page_data, dict):
            add(legacy_severity="high", page=slug or "site", issue_type="malformed_page",
                category="technical", title="Hibás oldalstruktúra",
                description="A CMS oldal nem objektum.", target=f"pages.{slug}",
                evidence={"target": f"pages.{slug}", "expected": "object",
                          "actual_type": type(page_data).__name__})
            continue

        seo = page_data.get("seo")
        if isinstance(seo, dict):
            seo_title = str(seo.get("title") or "").strip()
            seo_description = str(seo.get("description") or "").strip()
            if not seo_title:
                add(legacy_severity="medium", page=slug, issue_type="seo_title", category="seo",
                    title="Hiányzó SEO cím", description="Hiányzó SEO cím.", target="seo.title",
                    evidence={"target": "seo.title", "field": "title", "current_value": seo_title,
                              "expected": "Nem üres SEO cím."},
                    suggested_action={"action": "set_seo", "target": slug,
                                      "reason": "A keresőoldali megjelenéshez SEO cím szükséges."})
            elif len(seo_title) > 65:
                add(legacy_severity="low", page=slug, issue_type="seo_title_length", category="seo",
                    title="Túl hosszú SEO cím", description="A SEO cím 65 karakternél hosszabb.",
                    target="seo.title", evidence={"target": "seo.title", "field": "title",
                    "current_value": seo_title, "expected": "Legfeljebb 65 karakter.",
                    "details": {"length": len(seo_title), "maximum": 65}},
                    suggested_action={"action": "set_seo", "target": slug,
                                      "reason": "A SEO cím hosszát javasolt a megjelenési korláthoz igazítani."})
            if not seo_description:
                add(legacy_severity="medium", page=slug, issue_type="seo_description", category="seo",
                    title="Hiányzó meta leírás", description="Hiányzó meta leírás.",
                    target="seo.description", evidence={"target": "seo.description", "field": "description",
                    "current_value": seo_description, "expected": "Nem üres meta leírás."},
                    suggested_action={"action": "set_seo", "target": slug,
                                      "reason": "A keresőoldali kivonathoz meta leírás szükséges."})
            elif len(seo_description) > 165:
                add(legacy_severity="low", page=slug, issue_type="seo_description_length", category="seo",
                    title="Túl hosszú meta leírás", description="A meta leírás 165 karakternél hosszabb.",
                    target="seo.description", evidence={"target": "seo.description", "field": "description",
                    "current_value": seo_description, "expected": "Legfeljebb 165 karakter.",
                    "details": {"length": len(seo_description), "maximum": 165}},
                    suggested_action={"action": "set_seo", "target": slug,
                                      "reason": "A meta leírás hosszát javasolt a megjelenési korláthoz igazítani."})

        fields = page_data.get("fields", [])
        if not isinstance(fields, list):
            add(legacy_severity="high", page=slug, issue_type="malformed_fields", category="technical",
                title="Hibás fields struktúra", description="Az oldal fields értéke nem lista.",
                target=f"pages.{slug}.fields", evidence={"target": f"pages.{slug}.fields",
                "expected": "array", "actual_type": type(fields).__name__})
            fields = []
        for field_index, field in enumerate(fields):
            if not isinstance(field, dict):
                add(legacy_severity="high", page=slug, issue_type="malformed_field", category="technical",
                    title="Hibás CMS mező", description="A CMS mező nem objektum.",
                    target=f"fields.{field_index}", evidence={"target": f"fields.{field_index}",
                    "expected": "object", "actual_type": type(field).__name__})
                continue
            key = str(field.get("key") or f"field_{field_index}")
            value = str(field.get("value") or "")
            if key in REQUIRED_CONTENT_FIELD_ALLOWLIST and not value.strip():
                add(legacy_severity="medium", page=slug, issue_type="required_content_empty",
                    category="content", title="Kötelező címsor üres",
                    description=f"A kötelező {key} CMS mező üres.", target=f"fields.{key}",
                    evidence={"target": f"fields.{key}", "field": key, "current_value": value,
                              "expected": "Nem üres, H1-hez kötött tartalom."},
                    suggested_action={"action": "set_field", "target": slug,
                                      "reason": "A bizonyítottan kötelező oldalcím nem lehet üres."})
            if "http://" in value:
                add(legacy_severity="medium", page=slug, issue_type="insecure_link", category="links",
                    title="Nem biztonságos hivatkozás", description="Nem HTTPS hivatkozás található.",
                    target=f"fields.{key}", evidence={"target": f"fields.{key}", "field": key,
                    "current_value": value, "expected": "HTTPS hivatkozás."},
                    suggested_action={"action": "set_field", "target": slug,
                                      "reason": "A HTTP hivatkozást biztonságos HTTPS célra kell ellenőrizni."})

        blocks = page_data.get("blocks", [])
        if not isinstance(blocks, list):
            add(legacy_severity="high", page=slug, issue_type="malformed_blocks", category="technical",
                title="Hibás blocks struktúra", description="Az oldal blocks értéke nem lista.",
                target=f"pages.{slug}.blocks", evidence={"target": f"pages.{slug}.blocks",
                "expected": "array", "actual_type": type(blocks).__name__})
            continue
        for block_index, block in enumerate(blocks):
            if not isinstance(block, dict):
                add(legacy_severity="high", page=slug, issue_type="malformed_block", category="technical",
                    title="Hibás CMS blokk", description="A CMS blokk nem objektum.",
                    target=f"blocks.{block_index}", evidence={"target": f"blocks.{block_index}",
                    "expected": "object", "actual_type": type(block).__name__})
                continue
            target = _block_target(block, block_index)
            block_type = str(block.get("type") or "").strip().lower()
            if not block_type or block_type not in SUPPORTED_BLOCK_TYPES:
                add(legacy_severity="high", page=slug, issue_type="malformed_block_type",
                    category="technical", title="Hiányzó vagy ismeretlen blokktípus",
                    description="A CMS blokk típusa hiányzik vagy nem támogatott.", target=target,
                    evidence={"target": target, "block_index": block_index,
                              "actual_type": block.get("type"), "expected": sorted(SUPPORTED_BLOCK_TYPES)})
                continue
            for collection_key in ({"faq": "items", "buttons": "buttons"}.get(block_type),):
                if collection_key and not isinstance(block.get(collection_key), list):
                    add(legacy_severity="high", page=slug, issue_type="malformed_block_structure",
                        category="technical", title="Hibás blokkstruktúra",
                        description=f"A {block_type} blokk {collection_key} mezője nem lista.",
                        target=f"{target}.{collection_key}", evidence={"target": f"{target}.{collection_key}",
                        "block_index": block_index, "expected": "array",
                        "actual_type": type(block.get(collection_key)).__name__})

            if block_type in {"image", "video"}:
                source_field = "src"
                source_value = block.get("src")
                if block_type == "video" and not str(source_value or "").strip():
                    source_field = "url"
                    source_value = block.get("url")
                source = str(source_value or "").strip()
                if not source:
                    issue_type = "image_missing_src" if block_type == "image" else "video_missing_source"
                    add(legacy_severity="high", page=slug, issue_type=issue_type, category="media",
                        title="Hiányzó médiaforrás", description=f"A {block_type} blokk forrása hiányzik vagy üres.",
                        target=f"{target}.{source_field}", evidence={"target": f"{target}.{source_field}",
                        "block_index": block_index, "field": source_field,
                        "current_value": source_value, "expected": "Nem üres médiaforrás."},
                        suggested_action={"action": "review_missing_media", "target": slug,
                                          "reason": "A médiaforrást embernek kell ellenőriznie."})
                elif not EXTERNAL_URL.match(source):
                    media_path, path_error = _safe_upload_path(project_root, source)
                    if path_error:
                        add(legacy_severity="high", page=slug, issue_type="unsafe_media_path",
                            category="media", title="Nem biztonságos médiaútvonal",
                            description="A médiaútvonal kívül esik az engedélyezett uploads könyvtáron.",
                            target=f"{target}.{source_field}", evidence={"target": f"{target}.{source_field}",
                            "block_index": block_index, "field": source_field, "current_value": source,
                            "expected": "Relatív assets/uploads útvonal.", "reason": path_error})
                    elif media_path is not None and not media_path.is_file():
                        add(legacy_severity="high", page=slug, issue_type="missing_media",
                            category="media", title="Hiányzó médiafájl",
                            description=f"Hiányzó médiafájl: {source}",
                            target=f"{target}.{source_field}",
                            evidence={"target": f"{target}.{source_field}", "field": source_field,
                            "block_index": block_index, "current_value": source,
                            "expected": "Létező médiatári fájl."},
                            suggested_action={"action": "review_missing_media", "target": slug,
                                              "reason": "A hiányzó médiafájlt helyre kell állítani vagy a hivatkozást felül kell vizsgálni."})
                if block_type == "image" and source and not block.get("alt"):
                    add(legacy_severity="low", page=slug, issue_type="alt_text", category="accessibility",
                        title="Hiányzó ALT szöveg", description=f"Hiányzó alt szöveg: {source}",
                        target=source, evidence={"target": source, "field": "alt", "block_index": block_index,
                        "current_value": block.get("alt"), "expected": "Leíró ALT szöveg."},
                        suggested_action={"action": "review_alt_text", "target": slug,
                                          "reason": "A képhez akadálymentes és tartalmi szempontból megfelelő ALT szöveg szükséges."})
            for key in ("url", "link"):
                url = str(block.get(key) or "")
                if url.startswith("http://"):
                    add(legacy_severity="medium", page=slug, issue_type="insecure_link", category="links",
                        title="Nem biztonságos hivatkozás", description=f"Nem HTTPS hivatkozás: {url}",
                        target=f"{target}.{key}", evidence={"target": f"{target}.{key}", "field": key,
                        "block_index": block_index, "current_value": url, "expected": "HTTPS hivatkozás."},
                        suggested_action={"action": "review_link", "target": slug,
                                          "reason": "A HTTP hivatkozás HTTPS megfelelőjét ellenőrizni kell."})

    booking_url = config.get("booking_url", "") if isinstance(config, dict) else ""
    if not booking_url:
        add(legacy_severity="high", page="site", issue_type="booking_url", category="booking",
            title="Hiányzó időpontfoglalási URL", description="Nincs beállítva időpontfoglalási URL.",
            target="automation.booking_url", evidence={"target": "automation.booking_url",
            "field": "booking_url", "current_value": booking_url,
            "expected": "Jóváhagyott időpontfoglalási URL."},
            suggested_action={"action": "review_booking_url", "target": "site",
                              "reason": "A kritikus foglalási cél módosítása emberi felülvizsgálatot igényel."})
    detected.extend(detect_internal_html_links(project_root=project_root, detected_at=detected_at))
    return detected
