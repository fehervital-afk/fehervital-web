#!/usr/bin/env python3
"""Side-effect-free proposal data model for V19.3 P1.3a."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from automation_policy import redact

PROPOSAL_VERSION = 1
ALLOWED_SOURCES = {"deterministic", "ai_candidate"}
ALLOWED_DISPOSITIONS = {"proposable", "review_only", "blocked"}
ALLOWED_STATUSES = {"draft", "needs_review", "rejected", "stale", "blocked", "handed_off"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PROPOSAL_ID_RE = re.compile(r"^fp_[0-9a-f]{64}$")
DRIVE_RE = re.compile(r"^[A-Za-z]:")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def _validate_json_value(value: Any, *, field: str = "value") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field} contains a non-finite number.")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item, field=field)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{field} object keys must be strings.")
            _validate_json_value(item, field=field)
        return
    raise ValueError(f"{field} must be JSON-compatible.")


def canonical_json(value: Any) -> str:
    """Return strict deterministic JSON without changing value semantics."""
    _validate_json_value(value)
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    )


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def payload_hash(payload: Any) -> str:
    return canonical_hash(payload)


def evidence_hash(evidence: Any) -> str:
    return canonical_hash(evidence)


def snapshot_hash(resource_state: Any) -> str:
    return canonical_hash(resource_state)


def normalize_target(target: str) -> str:
    """Normalize a logical repository target; never resolve or access a path.

    Targets are trimmed, slash-normalized and lower-cased for stable identity.
    Absolute, drive, UNC, URL-like and traversal targets are rejected.
    """
    if not isinstance(target, str) or not target.strip():
        raise ValueError("Proposal target must be a non-empty string.")
    raw = target.strip()
    if raw.startswith(("/", "\\")) or DRIVE_RE.match(raw) or SCHEME_RE.match(raw):
        raise ValueError("Proposal target must be a safe logical target.")
    normalized = raw.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    parts = normalized.split("/")
    if not normalized or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Proposal target contains an unsafe path component.")
    return "/".join(parts).lower()


def stable_proposal_id(*, issue_id: str, action: str, target: str, payload: Any) -> str:
    if not isinstance(issue_id, str) or not issue_id.strip():
        raise ValueError("Proposal issue_id must be a non-empty string.")
    if not isinstance(action, str) or not action.strip():
        raise ValueError("Proposal action must be a non-empty string.")
    identity = {
        "issue_id": issue_id.strip(),
        "action": action.strip().lower(),
        "target": normalize_target(target),
        "payload": payload,
    }
    return "fp_" + canonical_hash(identity)


def _validate_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a valid ISO-8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone.")
    return value


def _validate_hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256 hash.")
    return value


@dataclass(frozen=True)
class CurrentSnapshot:
    resource: str
    value_hash: str
    resource_hash: str

    def __post_init__(self) -> None:
        normalize_target(self.resource)
        _validate_hash(self.value_hash, "current_snapshot.value_hash")
        _validate_hash(self.resource_hash, "current_snapshot.resource_hash")

    @classmethod
    def from_dict(cls, value: Any) -> "CurrentSnapshot":
        if not isinstance(value, dict) or set(value) != {"resource", "value_hash", "resource_hash"}:
            raise ValueError("Malformed current_snapshot.")
        return cls(**value)


@dataclass(frozen=True)
class PolicySnapshot:
    risk: str
    approval_required: bool
    autopilot_allowed: bool
    decision: str
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.risk, str) or not self.risk.strip():
            raise ValueError("policy.risk must be a non-empty string.")
        if type(self.approval_required) is not bool:
            raise ValueError("policy.approval_required must be boolean.")
        if type(self.autopilot_allowed) is not bool:
            raise ValueError("policy.autopilot_allowed must be boolean.")
        if not isinstance(self.decision, str) or not self.decision.strip():
            raise ValueError("policy.decision must be a non-empty string.")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("policy.reason must be a non-empty string.")

    @classmethod
    def from_dict(cls, value: Any) -> "PolicySnapshot":
        required = {"risk", "approval_required", "autopilot_allowed", "decision", "reason"}
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError("Malformed policy snapshot.")
        return cls(**value)


@dataclass(frozen=True)
class Proposal:
    proposal_version: int
    proposal_id: str
    issue_id: str
    issue_type: str
    source: str
    disposition: str
    action: str
    target: str
    payload: Any
    reason: str
    current_snapshot: CurrentSnapshot
    proposed_hash: str
    evidence_hash: str
    policy: PolicySnapshot
    status: str
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        if self.proposal_version != PROPOSAL_VERSION:
            raise ValueError("Unsupported proposal version.")
        if not isinstance(self.proposal_id, str) or not PROPOSAL_ID_RE.fullmatch(self.proposal_id):
            raise ValueError("Invalid proposal_id format.")
        for field in ("issue_id", "issue_type", "action", "reason"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a non-empty string.")
        if self.source not in ALLOWED_SOURCES:
            raise ValueError("Invalid proposal source.")
        if self.disposition not in ALLOWED_DISPOSITIONS:
            raise ValueError("Invalid proposal disposition.")
        if self.status not in ALLOWED_STATUSES:
            raise ValueError("Invalid proposal status.")
        normalized_target = normalize_target(self.target)
        _validate_json_value(self.payload, field="payload")
        _validate_hash(self.proposed_hash, "proposed_hash")
        _validate_hash(self.evidence_hash, "evidence_hash")
        _validate_timestamp(self.created_at, "created_at")
        _validate_timestamp(self.updated_at, "updated_at")
        expected_id = stable_proposal_id(
            issue_id=self.issue_id, action=self.action, target=normalized_target, payload=self.payload,
        )
        if self.proposal_id != expected_id:
            raise ValueError("proposal_id does not match proposal identity.")
        if self.proposed_hash != payload_hash(self.payload):
            raise ValueError("proposed_hash does not match payload.")

    def to_dict(self, *, display: bool = False) -> dict[str, Any]:
        value = asdict(self)
        return redact(value) if display else value

    def to_json(self, *, display: bool = False) -> str:
        return canonical_json(self.to_dict(display=display))

    @classmethod
    def from_dict(cls, value: Any) -> "Proposal":
        required = set(cls.__dataclass_fields__)
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError("Malformed proposal structure.")
        data = dict(value)
        data["current_snapshot"] = CurrentSnapshot.from_dict(data["current_snapshot"])
        data["policy"] = PolicySnapshot.from_dict(data["policy"])
        return cls(**data)

    @classmethod
    def from_json(cls, value: str) -> "Proposal":
        if not isinstance(value, str):
            raise ValueError("Proposal JSON must be a string.")
        try:
            parsed = json.loads(value, parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"Invalid JSON number: {item}")))
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("Malformed proposal JSON.") from exc
        return cls.from_dict(parsed)


def create_proposal(*, issue_id: str, issue_type: str, source: str, disposition: str,
                    action: str, target: str, payload: Any, reason: str,
                    current_snapshot: CurrentSnapshot, evidence_hash_value: str,
                    policy: PolicySnapshot, status: str, created_at: str,
                    updated_at: str) -> Proposal:
    normalized_target = normalize_target(target)
    return Proposal(
        proposal_version=PROPOSAL_VERSION,
        proposal_id=stable_proposal_id(
            issue_id=issue_id, action=action, target=normalized_target, payload=payload,
        ),
        issue_id=issue_id,
        issue_type=issue_type,
        source=source,
        disposition=disposition,
        action=action,
        target=normalized_target,
        payload=payload,
        reason=reason,
        current_snapshot=current_snapshot,
        proposed_hash=payload_hash(payload),
        evidence_hash=evidence_hash_value,
        policy=policy,
        status=status,
        created_at=created_at,
        updated_at=updated_at,
    )


def validate_proposal(value: Proposal | dict[str, Any]) -> Proposal:
    return value if isinstance(value, Proposal) else Proposal.from_dict(value)


def serialize_proposal(value: Proposal | dict[str, Any], *, display: bool = False) -> str:
    return validate_proposal(value).to_json(display=display)


def deserialize_proposal(value: str) -> Proposal:
    return Proposal.from_json(value)
