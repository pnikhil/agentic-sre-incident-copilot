"""Deterministic fault definitions and telemetry generators for the demo app.

Each fault produces a full telemetry snapshot (alert, metrics, logs, deployments,
ground truth) using fixed timestamps, so that the output is byte-stable and can
feed both the live demo and the evaluation golden set.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

SERVICE = "checkout-api"
INCIDENT_DATE = "2026-07-06"


class Fault(str, Enum):
    NONE = "none"
    BAD_DEPLOY = "bad_deploy"
    LATENCY_SPIKE = "latency_spike"


def _alert(alert_id: str, condition: str) -> dict[str, Any]:
    return {
        "id": alert_id,
        "service": SERVICE,
        "condition": condition,
        "severity": "high",
        "fired_at": f"{INCIDENT_DATE}T14:10:00Z",
        "labels": {"env": "production", "team": "checkout-platform"},
    }


def _bad_deploy() -> dict[str, Any]:
    return {
        "alert": _alert("alert-checkout-5xx-gen", "http_5xx_rate > 5% for 5m"),
        "metrics": {
            "service": SERVICE,
            "series": [
                {
                    "name": "http_5xx_rate",
                    "unit": "ratio",
                    "window": "1m",
                    "baseline": 0.003,
                    "points": [
                        {"ts": f"{INCIDENT_DATE}T13:55:00Z", "value": 0.002},
                        {"ts": f"{INCIDENT_DATE}T14:00:00Z", "value": 0.003},
                        {"ts": f"{INCIDENT_DATE}T14:05:00Z", "value": 0.081},
                        {"ts": f"{INCIDENT_DATE}T14:10:00Z", "value": 0.134},
                    ],
                }
            ],
        },
        "logs": [
            {"ts": f"{INCIDENT_DATE}T13:50:00Z", "level": "INFO", "service": SERVICE, "msg": "health check ok"},
            {"ts": f"{INCIDENT_DATE}T14:00:05Z", "level": "INFO", "service": SERVICE, "msg": "deployed revision checkout-api-00042"},
            {"ts": f"{INCIDENT_DATE}T14:05:12Z", "level": "ERROR", "service": SERVICE, "msg": "NullPointerException in CheckoutHandler.process"},
            {"ts": f"{INCIDENT_DATE}T14:06:03Z", "level": "ERROR", "service": SERVICE, "msg": "NullPointerException in CheckoutHandler.process"},
            {"ts": f"{INCIDENT_DATE}T14:07:41Z", "level": "ERROR", "service": SERVICE, "msg": "NullPointerException in CheckoutHandler.process"},
            {"ts": f"{INCIDENT_DATE}T14:08:55Z", "level": "ERROR", "service": SERVICE, "msg": "NullPointerException in CheckoutHandler.process"},
            {"ts": f"{INCIDENT_DATE}T14:09:37Z", "level": "ERROR", "service": SERVICE, "msg": "NullPointerException in CheckoutHandler.process"},
        ],
        "deployments": {
            "service": SERVICE,
            "deployments": [
                {"revision": "checkout-api-00041", "deployed_at": "2026-07-05T09:00:00Z", "status": "healthy"},
                {"revision": "checkout-api-00042", "deployed_at": f"{INCIDENT_DATE}T14:00:00Z", "status": "active", "previous_stable": "checkout-api-00041"},
            ],
        },
        "ground_truth": {
            "root_cause": "bad_deploy",
            "expected_action": "rollback_service",
            "expected_runbook": "checkout-bad-deploy-rollback",
            "required_evidence": ["error_rate_metric", "recent_deployment", "application_error_logs"],
        },
    }


def _latency_spike() -> dict[str, Any]:
    return {
        "alert": _alert("alert-checkout-latency-gen", "latency_p95 > 800ms for 5m"),
        "metrics": {
            "service": SERVICE,
            "series": [
                {
                    "name": "http_5xx_rate",
                    "unit": "ratio",
                    "window": "1m",
                    "baseline": 0.003,
                    "points": [
                        {"ts": f"{INCIDENT_DATE}T14:00:00Z", "value": 0.003},
                        {"ts": f"{INCIDENT_DATE}T14:05:00Z", "value": 0.006},
                        {"ts": f"{INCIDENT_DATE}T14:10:00Z", "value": 0.009},
                    ],
                },
                {
                    "name": "latency_p95",
                    "unit": "ms",
                    "window": "1m",
                    "baseline": 180.0,
                    "points": [
                        {"ts": f"{INCIDENT_DATE}T14:00:00Z", "value": 190.0},
                        {"ts": f"{INCIDENT_DATE}T14:05:00Z", "value": 640.0},
                        {"ts": f"{INCIDENT_DATE}T14:10:00Z", "value": 910.0},
                    ],
                },
            ],
        },
        "logs": [
            {"ts": f"{INCIDENT_DATE}T14:05:11Z", "level": "WARN", "service": SERVICE, "msg": "request queue depth high"},
            {"ts": f"{INCIDENT_DATE}T14:08:20Z", "level": "WARN", "service": SERVICE, "msg": "request queue depth high"},
        ],
        "deployments": {
            "service": SERVICE,
            "deployments": [
                {"revision": "checkout-api-00041", "deployed_at": "2026-07-05T09:00:00Z", "status": "healthy"}
            ],
        },
        "ground_truth": {
            "root_cause": "resource_saturation",
            "expected_action": "scale_service",
            "expected_runbook": "checkout-latency-scaling",
            "required_evidence": ["latency_metric"],
        },
    }


def _healthy() -> dict[str, Any]:
    return {
        "alert": _alert("alert-checkout-noop-gen", "synthetic canary"),
        "metrics": {
            "service": SERVICE,
            "series": [
                {
                    "name": "http_5xx_rate",
                    "unit": "ratio",
                    "window": "1m",
                    "baseline": 0.003,
                    "points": [
                        {"ts": f"{INCIDENT_DATE}T14:00:00Z", "value": 0.002},
                        {"ts": f"{INCIDENT_DATE}T14:05:00Z", "value": 0.003},
                    ],
                }
            ],
        },
        "logs": [
            {"ts": f"{INCIDENT_DATE}T14:00:00Z", "level": "INFO", "service": SERVICE, "msg": "health check ok"}
        ],
        "deployments": {
            "service": SERVICE,
            "deployments": [
                {"revision": "checkout-api-00041", "deployed_at": "2026-07-05T09:00:00Z", "status": "healthy"}
            ],
        },
        "ground_truth": {"root_cause": "none", "expected_action": "none"},
    }


def generate(fault: Fault) -> dict[str, Any]:
    """Return a full, deterministic telemetry snapshot for the given fault."""
    if fault == Fault.BAD_DEPLOY:
        return _bad_deploy()
    if fault == Fault.LATENCY_SPIKE:
        return _latency_spike()
    return _healthy()
