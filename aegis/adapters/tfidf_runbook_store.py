from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

from ..domain.schemas import RunbookDoc, RunbookHit
from ..ports.runbook_store import RunbookStorePort
from .local_runbook_store import LocalRunbookStore

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _chunk(doc: RunbookDoc) -> list[str]:
    """Semantic chunking. The title along with the applies_when clauses, and each
    markdown section, become separate chunks, so that retrieval can match the
    most relevant part of a runbook rather than the whole document."""
    chunks: list[str] = []
    header = doc.title
    if doc.applies_when:
        header = header + " " + " ".join(doc.applies_when)
    chunks.append(header)
    for part in re.split(r"\n(?=#)", doc.body):
        part = part.strip()
        if part:
            chunks.append(part)
    return chunks


class TfidfRunbookStore(RunbookStorePort):
    """A local vector store for runbooks. It builds TF-IDF vectors over
    semantically chunked runbooks and ranks them by cosine similarity.

    Fully offline and deterministic. No model download, no vector database.
    A pgvector or Vertex Vector Search adapter can replace it later.
    """

    def __init__(self, runbooks_dir: Path):
        self.docs: dict[str, RunbookDoc] = {}
        for path in sorted(Path(runbooks_dir).glob("*.md")):
            doc = LocalRunbookStore._load(path)
            self.docs[doc.id] = doc

        self._chunks: list[tuple[str, list[str]]] = []
        for doc in self.docs.values():
            for chunk in _chunk(doc):
                self._chunks.append((doc.id, _tokenize(chunk)))
        self._idf = self._build_idf()
        self._vectors = [(rid, self._vectorize(tokens)) for rid, tokens in self._chunks]

    def _build_idf(self) -> dict[str, float]:
        total = len(self._chunks) or 1
        doc_freq: Counter = Counter()
        for _rid, tokens in self._chunks:
            for term in set(tokens):
                doc_freq[term] += 1
        return {t: math.log((1 + total) / (1 + df)) + 1.0 for t, df in doc_freq.items()}

    def _vectorize(self, tokens: list[str]) -> dict[str, float]:
        if not tokens:
            return {}
        counts = Counter(tokens)
        vec = {t: (c / len(tokens)) * self._idf.get(t, 0.0) for t, c in counts.items()}
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        return {t: w / norm for t, w in vec.items()}

    def search(self, query: str, *, limit: int = 5) -> list[RunbookHit]:
        query_vec = self._vectorize(_tokenize(query))
        best: dict[str, float] = {}
        for rid, chunk_vec in self._vectors:
            score = sum(query_vec.get(t, 0.0) * w for t, w in chunk_vec.items())
            if score > best.get(rid, 0.0):
                best[rid] = score
        hits = [
            RunbookHit(runbook_id=rid, score=round(score, 4), snippet=self.docs[rid].title)
            for rid, score in best.items()
        ]
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    def get(self, runbook_id: str) -> RunbookDoc | None:
        return self.docs.get(runbook_id)
