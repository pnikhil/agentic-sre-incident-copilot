from __future__ import annotations

import re
from pathlib import Path

import yaml

from ..domain.schemas import RunbookDoc, RunbookHit
from ..ports.runbook_store import RunbookStorePort

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


class LocalRunbookStore(RunbookStorePort):
    """Loads a local markdown runbook corpus and does keyword retrieval, without any vector DB."""

    def __init__(self, runbooks_dir: Path):
        self.docs: dict[str, RunbookDoc] = {}
        for path in sorted(Path(runbooks_dir).glob("*.md")):
            doc = self._load(path)
            self.docs[doc.id] = doc

    @staticmethod
    def _load(path: Path) -> RunbookDoc:
        raw = path.read_text(encoding="utf-8")
        match = _FRONTMATTER_RE.match(raw)
        if not match:
            return RunbookDoc(id=path.stem, title=path.stem, body=raw, path=str(path))
        meta = yaml.safe_load(match.group(1)) or {}
        body = match.group(2).strip()
        return RunbookDoc(
            path=str(path),
            body=body,
            id=str(meta.get("id", path.stem)),
            title=str(meta.get("title", path.stem)),
            owner=meta.get("owner"),
            approved=bool(meta.get("approved", True)),
            environment_scope=list(meta.get("environment_scope") or []),
            last_reviewed=str(meta["last_reviewed"]) if meta.get("last_reviewed") else None,
            expires_at=str(meta["expires_at"]) if meta.get("expires_at") else None,
            applies_when=list(meta.get("applies_when") or []),
            exit_when=list(meta.get("exit_when") or []),
            required_evidence=list(meta.get("required_evidence") or []),
            evidence_recipe=list(meta.get("evidence_recipe") or []),
            allowed_actions=list(meta.get("allowed_actions") or []),
            risk_level=str(meta.get("risk_level", "unknown")),
            requires_approval=bool(meta.get("requires_approval", True)),
        )

    def search(self, query: str, *, limit: int = 5) -> list[RunbookHit]:
        query_tokens = _tokenize(query)
        hits: list[RunbookHit] = []
        for doc in self.docs.values():
            corpus = " ".join([doc.title, doc.body, *doc.applies_when])
            score = float(len(query_tokens & _tokenize(corpus)))
            hits.append(RunbookHit(runbook_id=doc.id, score=score, snippet=doc.title))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    def get(self, runbook_id: str) -> RunbookDoc | None:
        return self.docs.get(runbook_id)
