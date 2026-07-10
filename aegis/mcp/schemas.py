"""Typed input and result schemas for the diagnostic tools.

These schemas are the shared tool contract for the gateway and FastMCP server.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..domain.schemas import RunbookDoc


class FetchMetricsInput(BaseModel):
    scenario: str
    service: str
    signal: str = "http_5xx_rate"
    window: str = "15m"


class QueryLogsInput(BaseModel):
    scenario: str
    service: str
    query: str = "ERROR OR 5xx OR exception"


class GetDeploymentsInput(BaseModel):
    scenario: str
    service: str
    window: str = "2h"


class SearchRunbooksInput(BaseModel):
    query: str
    limit: int = 3


class MetricsResult(BaseModel):
    service: str
    series: list[dict] = Field(default_factory=list)


class LogsResult(BaseModel):
    service: str
    entries: list[dict] = Field(default_factory=list)


class DeploymentsResult(BaseModel):
    service: str
    deployments: list[dict] = Field(default_factory=list)


class RunbookSearchResult(BaseModel):
    hits: list[RunbookDoc] = Field(default_factory=list)
