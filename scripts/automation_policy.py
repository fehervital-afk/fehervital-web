#!/usr/bin/env python3
"""Central, fail-closed policy and audit primitives for V19.3 automation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUDIT_LOG = ROOT / "assets" / "content" / "automation_audit.json"
PAGES_JSON = ROOT / "assets" / "content" / "pages.json"

RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "BLOCKED": 3}

# This code registry is authoritative. JSON configuration may only make policy
# stricter; it cannot downgrade these decisions.
ACTION_REGISTRY = {
    "audit_site": {
        "risk": "LOW",
        "approval_required": False,
        "autopilot_allowed": True,
        "target_types": {"site"},
        "max_changes": 1,
    },
    "set_field": {
        "risk": "MEDIUM",
        "approval_required": True,
        "autopilot_allowed": False,
        "target_types": {"cms_page"},
        "max_changes": 10,
    },
    "add_block": {
        "risk": "MEDIUM",
        "approval_required": True,
        "autopilot_allowed": False,
        "target_types": {"cms_page"},
        "max_changes": 5,
    },
    "set_seo": {
        "risk": "MEDIUM",
        "approval_required": True,
        "autopilot_allowed": False,
        "target_types": {"cms_page"},
        "max_changes": 10,
    },
    "publish": {
        "risk": "HIGH",
        "approval_required": True,
        "autopilot_allowed": False,
        "target_types": {"production"},
        "max_changes": 1,
    },
}

PROTECTED_PATH_PATTERNS = (
    r"(^|/)\.git(/|$)", r"(^|/)\.github(/|$)", r"(^|/)\.env[^/]*$",
    r"(^|/)render(?:\.yaml|\.yml|/|$)", r"(^|/)scripts/build_public\.py$",
    r"(^|/)assets/js/app\.js$", r"(^|/)adatkezeles\.html$",
    r"(^|/)local_admin_server\.py$",
)
PROTECTED_KEYWORDS = {
    "domain", "email", "phone", "telephone", "booking_url", "booking",
    "contact", "official_email", "host", "hostname", "maintenance",
    "deploy", "workflow", "secret", "api_key", "token",
}
PROTECTED_VALUE_MARKERS = (
    "fehervital.hu", "info@fehervital.hu", "recepciosai.hu",
)
CMS_PAGE_TARGETS = {
    "index", "biorezonancia", "harmonyscan", "ai", "kapcsolat", "recepcios_ai",
    "egeszsegpont", "termekek", "oxigenkoncentrator", "lagy_lezer",
    "vorosfenyu_hajapolo_sisak", "adatkezeles", "idopontfoglalas",
}
SENSITIVE_CMS_TARGETS = {"kapcsolat", "idopontfoglalas"}
BLOCKED_CMS_TARGETS = {"adatkezeles"}
ALLOWED_BLOCK_TYPES = {"text", "image", "video", "iconbox", "testimonial", "price", "buttons", "divider", "cta", "faq"}
CANONICAL_SITE_TARGETS = {"site"}
MANUAL_PUBLISH_TARGET = "production"
MANUAL_PUBLISH_ACTORS = {"local_admin"}


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    action: str
    target: str
    target_type: str
    risk: str
    approval_required: bool
    autopilot_allowed: bool
    protected: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _contains_secret_key(name: str) -> bool:
    lowered = name.lower()
    return any(x in lowered for x in ("secret", "api_key", "apikey", "password", "authorization", "token"))


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): "[REDACTED]" if _contains_secret_key(str(k)) else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)bearer\s+[A-Za-z0-9._-]+", "Bearer [REDACTED]", value)
        value = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", value)
    return value


def write_audit_event(event: str, *, task_id: str = "", actor: str = "system",
                      action: str = "", target: str = "", policy_risk: str = "",
                      result: str = "", reason: str = "", details: Any = None,
                      path: Path | None = None) -> dict[str, Any]:
    target_path = path or AUDIT_LOG
    try:
        data = json.loads(target_path.read_text(encoding="utf-8"))
    except Exception:
        data = {"version": 1, "entries": []}
    entry = {
        "timestamp": utcnow(), "event": event, "task_id": str(task_id or ""),
        "actor": str(actor or "system"), "action": str(action or ""),
        "target": str(target or ""), "policy_risk": str(policy_risk or ""),
        "result": str(result or ""), "reason": str(reason or ""),
    }
    if details is not None:
        entry["details"] = redact(details)
    data.setdefault("entries", []).append(redact(entry))
    data["entries"] = data["entries"][-1000:]
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return entry


def content_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _protected_path(target: str) -> bool:
    normalized = str(target or "").replace("\\", "/").lower()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.lstrip("/")
    return any(re.search(pattern, normalized, flags=re.I) for pattern in PROTECTED_PATH_PATTERNS)


def _walk_strings(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)
    elif value is not None:
        yield str(value)


def _sensitive_cms_change(request: dict[str, Any]) -> bool:
    key = str(request.get("key") or "").lower()
    if any(word in key for word in PROTECTED_KEYWORDS):
        return True
    payload = request.get("value") if "value" in request else request.get("block", request.get("seo", {}))
    strings = [text.lower() for text in _walk_strings(payload)]
    return any(marker in text for marker in PROTECTED_VALUE_MARKERS for text in strings)


def _contains_protected_current_value(value: Any) -> bool:
    strings = [text.lower() for text in _walk_strings(value)]
    for text in strings:
        if any(marker in text for marker in PROTECTED_VALUE_MARKERS):
            return True
        if re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, flags=re.I):
            return True
        if re.search(r"(?<!\d)(?:\+36|06)[\s()/.\-]*\d(?:[\s()/.\-]*\d){7,10}(?!\d)", text):
            return True
    return False


def _canonical_current_value(request: dict[str, Any]) -> tuple[bool, Any, str]:
    """Resolve only an allow-listed CMS value from the fixed pages.json path."""
    target = request.get("target", request.get("page", ""))
    if target not in CMS_PAGE_TARGETS:
        return False, None, "Unknown CMS target."
    try:
        data = json.loads(PAGES_JSON.read_text(encoding="utf-8"))
    except Exception:
        return False, None, "Canonical CMS data is unavailable."
    page = (data.get("pages") or {}).get(target)
    if not isinstance(page, dict):
        return False, None, "Canonical CMS target is unavailable."
    action = request.get("action")
    if action == "set_field":
        key = request.get("key")
        for field in page.get("fields") or []:
            if isinstance(field, dict) and field.get("key") == key:
                return True, field.get("value"), "Current CMS field resolved."
        return False, None, "Canonical CMS field is unavailable."
    if action == "set_seo":
        seo = page.get("seo")
        if not isinstance(seo, dict):
            return False, None, "Canonical CMS SEO data is unavailable."
        keys = set((request.get("seo") or {}).keys())
        return True, {key: seo.get(key) for key in keys}, "Current CMS SEO data resolved."
    return True, None, "Action does not replace an existing CMS value."


def evaluate_action(request: Any, *, approved: bool = False, actor: str = "system",
                    autopilot: bool = False) -> PolicyDecision:
    if not isinstance(request, dict):
        return PolicyDecision(False, "", "", "", "BLOCKED", True, False, False, "Invalid action schema.")
    action = request.get("action")
    target = request.get("target", request.get("page", ""))
    target_type = request.get("target_type", "site" if action == "audit_site" else "cms_page")
    if not isinstance(action, str) or not action or not isinstance(target, str) or not target:
        return PolicyDecision(False, str(action or ""), str(target or ""), str(target_type or ""), "BLOCKED", True, False, False, "Missing action or target.")
    rule = ACTION_REGISTRY.get(action)
    if not rule:
        return PolicyDecision(False, action, target, str(target_type), "BLOCKED", True, False, False, "Unknown action; fail closed.")
    if target_type not in rule["target_types"]:
        return PolicyDecision(False, action, target, str(target_type), "BLOCKED", True, False, False, "Target type is not allowed for this action.")
    if action == "audit_site" and target not in CANONICAL_SITE_TARGETS:
        return PolicyDecision(False, action, target, str(target_type), "BLOCKED", True, False, False, "Unknown site audit target.")
    if action == "publish":
        if target != MANUAL_PUBLISH_TARGET:
            return PolicyDecision(False, action, target, str(target_type), "BLOCKED", True, False, True, "Unknown production publish target.")
        if autopilot or actor not in MANUAL_PUBLISH_ACTORS:
            return PolicyDecision(False, action, target, str(target_type), "BLOCKED", True, False, True, "Programmatic production publish is blocked by policy.")
    if _protected_path(target):
        return PolicyDecision(False, action, target, str(target_type), "BLOCKED", True, False, True, "Protected file or resource.")
    if target_type == "cms_page" and target not in CMS_PAGE_TARGETS:
        return PolicyDecision(False, action, target, str(target_type), "BLOCKED", True, False, False, "Unknown CMS target.")
    if target in BLOCKED_CMS_TARGETS:
        return PolicyDecision(False, action, target, str(target_type), "BLOCKED", True, False, True, "Legal CMS content is protected.")
    if action == "set_field" and (not isinstance(request.get("key"), str) or "value" not in request):
        return PolicyDecision(False, action, target, str(target_type), "BLOCKED", True, False, False, "Invalid set_field schema.")
    if action == "add_block" and (not isinstance(request.get("block"), dict)
                                  or request["block"].get("type") not in ALLOWED_BLOCK_TYPES):
        return PolicyDecision(False, action, target, str(target_type), "BLOCKED", True, False, False, "Invalid add_block schema.")
    if action == "set_seo" and (not isinstance(request.get("seo"), dict)
                                or not request["seo"]
                                or any(k not in {"title", "description", "keywords", "og_image"} for k in request["seo"])):
        return PolicyDecision(False, action, target, str(target_type), "BLOCKED", True, False, False, "Invalid set_seo schema.")

    request_sensitive = target in SENSITIVE_CMS_TARGETS or _sensitive_cms_change(request)
    current_protected = False
    if action in {"set_field", "set_seo"}:
        current_found, current_value, current_reason = _canonical_current_value(request)
        if not current_found and not request_sensitive:
            return PolicyDecision(False, action, target, str(target_type), "BLOCKED", True, False, False, current_reason)
        current_protected = current_found and _contains_protected_current_value(current_value)

    risk = str(rule["risk"])
    protected = False
    if target_type == "cms_page" and (request_sensitive or current_protected):
        risk, protected = "HIGH", True
    approval_required = bool(rule["approval_required"] or risk in {"MEDIUM", "HIGH", "BLOCKED"})
    autopilot_allowed = bool(rule["autopilot_allowed"] and risk == "LOW" and not protected)

    if autopilot and not autopilot_allowed:
        return PolicyDecision(False, action, target, str(target_type), risk, approval_required, False, protected, "Action is not eligible for Autopilot.")
    if approval_required and not approved:
        return PolicyDecision(False, action, target, str(target_type), risk, True, autopilot_allowed, protected, "Human approval is required.")
    return PolicyDecision(True, action, target, str(target_type), risk, approval_required, autopilot_allowed, protected, "Policy requirements satisfied.")


def evaluate_plan(plan: Any, *, approved: bool = False, actor: str = "system",
                  autopilot: bool = False) -> dict[str, Any]:
    if not isinstance(plan, dict) or not isinstance(plan.get("changes"), list):
        return {"allowed": False, "risk": "BLOCKED", "approval_required": True,
                "autopilot_allowed": False, "reason": "Invalid plan schema.", "decisions": []}
    changes = plan["changes"]
    if not changes:
        return {"allowed": True, "risk": "LOW", "approval_required": False,
                "autopilot_allowed": False, "reason": "No mutating actions.", "decisions": []}
    action_counts: dict[str, int] = {}
    for change in changes:
        if isinstance(change, dict):
            name = str(change.get("action") or "")
            action_counts[name] = action_counts.get(name, 0) + 1
    over_scope = [name for name, count in action_counts.items()
                  if name in ACTION_REGISTRY and count > int(ACTION_REGISTRY[name]["max_changes"])]
    if over_scope:
        return {"allowed": False, "risk": "BLOCKED", "approval_required": True,
                "autopilot_allowed": False, "protected": False,
                "reason": "Maximum action scope exceeded: " + ", ".join(over_scope), "decisions": []}
    decisions = [evaluate_action(change, approved=approved, actor=actor, autopilot=autopilot) for change in changes]
    risk = max((d.risk for d in decisions), key=lambda x: RISK_ORDER[x], default="BLOCKED")
    allowed = all(d.allowed for d in decisions)
    return {
        "allowed": allowed,
        "risk": risk,
        "approval_required": any(d.approval_required for d in decisions),
        "autopilot_allowed": bool(decisions) and all(d.autopilot_allowed for d in decisions),
        "protected": any(d.protected for d in decisions),
        "reason": "Policy requirements satisfied." if allowed else " | ".join(d.reason for d in decisions if not d.allowed),
        "decisions": [d.to_dict() for d in decisions],
    }
