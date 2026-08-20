#!/usr/bin/env python3
"""Versioned unified issue model for the V19.3 AI Webmaster workflow."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from automation_policy import redact

ISSUE_SCHEMA_VERSION = 1
ALLOWED_SEVERITIES = {"info", "warning", "error", "critical"}
ALLOWED_STATUSES = {"open", "acknowledged", "planned", "resolved", "ignored"}
ALLOWED_DETECTORS = {"deterministic", "ai", "manual"}
ALLOWED_POLICY_RISKS = {"LOW", "MEDIUM", "HIGH", "BLOCKED", "UNKNOWN"}

LEGACY_SEVERITY_MAP = {
    "low": "info",
    "medium": "warning",
    "high": "error",
    "critical": "critical",
}

CATEGORY_BY_TYPE = {
    "seo_title": "seo",
    "seo_title_length": "seo",
    "seo_description": "seo",
    "seo_description_length": "seo",
    "alt_text": "accessibility",
    "missing_media": "media",
    "insecure_link": "links",
    "booking_url": "booking",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_identity_part(value: Any) -> str:
    text = str(value or "").strip().lower().replace("\\", "/")
    text = re.sub(r"\s+", " ", text)
    return text


def stable_issue_id(*, page: str, category: str, issue_type: str, target: str = "",
                    case_sensitive_identity: str | None = None) -> str:
    canonical = "|".join(_normalize_identity_part(value) for value in (page, category, target, issue_type))
    if case_sensitive_identity is not None:
        canonical += "|case-sensitive:" + case_sensitive_identity
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"wm_{digest}"


def validate_issue(issue: Any) -> dict[str, Any]:
    if not isinstance(issue, dict):
        raise ValueError("Issue must be an object.")
    required = {
        "schema_version", "issue_id", "page", "category", "severity", "title",
        "description", "evidence", "detected_by", "detected_at",
        "suggested_action", "policy_risk", "status",
    }
    missing = sorted(required - set(issue))
    if missing:
        raise ValueError("Missing issue fields: " + ", ".join(missing))
    if issue["schema_version"] != ISSUE_SCHEMA_VERSION:
        raise ValueError("Unsupported issue schema version.")
    if issue["severity"] not in ALLOWED_SEVERITIES:
        raise ValueError("Invalid issue severity.")
    if issue["status"] not in ALLOWED_STATUSES:
        raise ValueError("Invalid issue status.")
    if issue["detected_by"] not in ALLOWED_DETECTORS:
        raise ValueError("Invalid issue detector.")
    if issue["policy_risk"] not in ALLOWED_POLICY_RISKS:
        raise ValueError("Invalid issue policy risk.")
    if not isinstance(issue["evidence"], (dict, list)):
        raise ValueError("Issue evidence must be a structured object or list.")
    if issue["suggested_action"] is not None and not isinstance(issue["suggested_action"], dict):
        raise ValueError("Suggested action must be an object or null.")
    for field in ("issue_id", "page", "category", "title", "description", "detected_at"):
        if not isinstance(issue[field], str) or not issue[field].strip():
            raise ValueError(f"Issue field {field} must be a non-empty string.")
    return issue


def create_issue(*, page: str, category: str, issue_type: str, severity: str,
                 title: str, description: str, evidence: dict[str, Any] | list[Any],
                 detected_by: str = "deterministic", detected_at: str | None = None,
                 suggested_action: dict[str, Any] | None = None,
                 policy_risk: str = "UNKNOWN", status: str = "open",
                 target: str = "", legacy_severity: str | None = None,
                 case_sensitive_identity: str | None = None) -> dict[str, Any]:
    timestamp = detected_at or utcnow()
    safe_evidence = redact(evidence)
    safe_action = redact(suggested_action) if suggested_action is not None else None
    safe_title = redact(title)
    safe_description = redact(description)
    issue = {
        "schema_version": ISSUE_SCHEMA_VERSION,
        "issue_id": stable_issue_id(
            page=page, category=category, issue_type=issue_type, target=target,
            case_sensitive_identity=case_sensitive_identity,
        ),
        "page": page,
        "category": category,
        "severity": severity,
        "title": safe_title,
        "description": safe_description,
        "evidence": safe_evidence,
        "detected_by": detected_by,
        "detected_at": timestamp,
        "last_seen_at": timestamp,
        "resolved_at": None,
        "suggested_action": safe_action,
        "policy_risk": policy_risk,
        "status": status,
        # Compatibility fields consumed by the current admin and older tools.
        "type": issue_type,
        "message": safe_description,
    }
    if legacy_severity:
        issue["legacy_severity"] = legacy_severity
    return validate_issue(issue)


def _legacy_target(item: dict[str, Any]) -> str:
    issue_type = str(item.get("type") or "legacy")
    if issue_type == "seo_title":
        return "seo.title"
    if issue_type == "seo_description":
        return "seo.description"
    if issue_type in {"seo_title_length", "seo_description_length"}:
        return "seo.title" if "title" in issue_type else "seo.description"
    message = str(item.get("message") or "")
    if issue_type in {"alt_text", "missing_media"} and ":" in message:
        return message.split(":", 1)[1].strip()
    return issue_type


def coerce_existing_issue(item: Any, *, fallback_detected_at: str) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    if item.get("schema_version") == ISSUE_SCHEMA_VERSION and item.get("issue_id"):
        candidate = redact(dict(item))
        candidate.setdefault("last_seen_at", candidate.get("detected_at") or fallback_detected_at)
        candidate.setdefault("resolved_at", None)
        try:
            return validate_issue(candidate)
        except ValueError:
            return None
    issue_type = str(item.get("type") or "legacy_issue")
    legacy_severity = str(item.get("severity") or "medium").lower()
    severity = LEGACY_SEVERITY_MAP.get(legacy_severity, "warning")
    page = str(item.get("page") or "site")
    description = str(item.get("message") or "Legacy audit issue.")
    return create_issue(
        page=page,
        category=CATEGORY_BY_TYPE.get(issue_type, "technical"),
        issue_type=issue_type,
        severity=severity,
        title=description,
        description=description,
        evidence={"target": _legacy_target(item), "details": {"migrated_from_legacy": True}},
        detected_at=fallback_detected_at,
        target=_legacy_target(item),
        legacy_severity=legacy_severity,
    )


def merge_issue_lifecycle(previous_items: list[Any], detected_items: list[dict[str, Any]], *,
                          now: str | None = None, previous_detected_at: str | None = None) -> list[dict[str, Any]]:
    timestamp = now or utcnow()
    fallback = previous_detected_at or timestamp
    existing: dict[str, dict[str, Any]] = {}
    existing_order: list[str] = []
    for raw in previous_items:
        item = coerce_existing_issue(raw, fallback_detected_at=fallback)
        if not item or item["issue_id"] in existing:
            continue
        existing[item["issue_id"]] = item
        existing_order.append(item["issue_id"])

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in detected_items:
        current = validate_issue(redact(dict(raw)))
        issue_id = current["issue_id"]
        if issue_id in seen:
            continue
        seen.add(issue_id)
        old = existing.get(issue_id)
        if old:
            current["detected_at"] = old["detected_at"]
            current["last_seen_at"] = timestamp
            previous_status = old.get("status")
            if previous_status in {"open", "acknowledged", "planned", "ignored"}:
                current["status"] = previous_status
            else:
                current["status"] = "open"
            current["resolved_at"] = None
        else:
            current["last_seen_at"] = timestamp
        merged.append(validate_issue(current))

    for issue_id in existing_order:
        if issue_id in seen:
            continue
        old = existing[issue_id]
        if old.get("status") == "ignored":
            merged.append(old)
            continue
        if old.get("status") != "resolved":
            old["status"] = "resolved"
            old["resolved_at"] = timestamp
        merged.append(validate_issue(old))
    return merged


def serialize_issue(issue: dict[str, Any]) -> str:
    return json.dumps(validate_issue(redact(dict(issue))), ensure_ascii=False, sort_keys=True)
