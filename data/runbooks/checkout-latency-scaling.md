---
id: checkout-latency-scaling
title: Checkout API latency scaling
owner: checkout-platform
last_reviewed: 2026-06-01
expires_at: 2026-12-01
approved: true
environment_scope: [production]
applies_when:
  - latency p95 elevated without a recent deployment
exit_when:
  - error rate spike correlates with a recent deployment
required_evidence:
  - latency_metric
evidence_recipe:
  - { tool: fetch_metrics, signal: latency_p95, window: 15m }
allowed_actions:
  - scale_service
risk_level: low
requires_approval: true
---

# Checkout API — Latency Scaling

Elevated p95 latency without a recent deploy usually indicates resource saturation under
load. Scale the service out to add capacity and relieve queueing.
