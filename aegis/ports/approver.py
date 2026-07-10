from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.schemas import ApprovalRequest, ApprovalStatus, Incident, RemediationProposal


class ApprovalDecisionPort(ABC):
    """The human-in-the-loop decision. In the approved_writes mode, the workflow
    asks this port whether to go ahead with the proposed rollback.

    Kindly note that a decision of PENDING means no human has decided yet, so the
    workflow stops and waits, rather than acting.
    """

    @abstractmethod
    def decide(
        self, *, approval: ApprovalRequest, proposal: RemediationProposal, incident: Incident
    ) -> ApprovalStatus:
        ...
