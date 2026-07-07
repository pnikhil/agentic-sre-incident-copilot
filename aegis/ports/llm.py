from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.schemas import (
    Alert,
    CriticOpinion,
    Diagnosis,
    EvidenceStack,
    RemediationProposal,
    RunbookDoc,
)


class LLMPort(ABC):
    """The reasoning port. For now a mock adapter is used, and a Vertex AI Gemini adapter will come in a later milestone."""

    @abstractmethod
    def diagnose(
        self, *, alert: Alert, evidence: EvidenceStack, runbook: RunbookDoc | None
    ) -> Diagnosis:
        ...

    @abstractmethod
    def critique(
        self,
        *,
        alert: Alert,
        diagnosis: Diagnosis,
        proposal: RemediationProposal,
        evidence: EvidenceStack,
        runbook: RunbookDoc | None,
    ) -> CriticOpinion:
        ...
