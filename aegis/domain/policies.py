"""Domain policies: the priority order, the named invariants, and the grounding plus hashing helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any

from .schemas import Diagnosis, DiagnosisStatus, RunbookDoc

# Ties are always broken in this order.
PRIORITY_ORDER = [
    "hard safety policy",
    "approval state",
    "current telemetry evidence",
    "approved runbook",
    "historical memory",
    "model reasoning",
]

# The named invariants.
INVARIANTS = (
    "No Evidence -> No Diagnosis; "
    "No Approved Runbook Quote -> No Remediation Proposal; "
    "No Policy Pass + Valid Approval -> No Write."
)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha256_of(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def quote_is_grounded(quote: str, source_text: str) -> bool:
    """Verifiable groundedness. The quote must actually exist in the source."""
    if not quote or not source_text:
        return False
    return _normalize(quote) in _normalize(source_text)


def has_cited_evidence(diagnosis: Diagnosis) -> bool:
    """No Evidence -> No Diagnosis."""
    return diagnosis.status == DiagnosisStatus.CONFIRMED and bool(diagnosis.cited_evidence_ids)


def action_allowed(action: str, runbook: RunbookDoc | None) -> bool:
    return bool(runbook) and action in runbook.allowed_actions


def runbook_usable(runbook: RunbookDoc | None) -> tuple[bool, str]:
    """Stale or unapproved runbooks may be cited as background, but they cannot authorise any action."""
    if runbook is None:
        return False, "no runbook"
    if not runbook.approved:
        return False, "runbook not approved"
    if runbook.expires_at:
        try:
            if date.fromisoformat(str(runbook.expires_at)) < datetime.now(timezone.utc).date():
                return False, "runbook expired"
        except ValueError:
            pass
    return True, "ok"
