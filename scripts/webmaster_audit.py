#!/usr/bin/env python3
"""Deterministic, local-only website audit detectors.

The engine accepts already loaded CMS/config data and may only inspect media
below the fixed project root. It never writes files, uses the network, calls an
AI service, evaluates policy, or executes a suggested action.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

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
    return detected
