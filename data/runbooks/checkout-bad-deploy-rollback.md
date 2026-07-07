---
id: checkout-bad-deploy-rollback
title: Checkout API bad deploy rollback
owner: checkout-platform
last_reviewed: 2026-06-01
expires_at: 2026-12-01
approved: true
environment_scope: [production, staging]
applies_when:
  - error_rate increased after recent deployment
  - logs show 5xx after revision change
exit_when:
  - no deployment occurred within incident window
  - errors started before deployment
required_evidence:
  - error_rate_metric
  - recent_deployment
  - application_error_logs
evidence_recipe:
  - { tool: fetch_metrics, signal: http_5xx_rate, window: 15m }
  - { tool: get_recent_deployments, window: 2h }
  - { tool: query_logs, query: "ERROR OR 5xx OR exception" }
allowed_actions:
  - rollback_service
risk_level: medium
requires_approval: true
---

# Checkout API — Bad Deploy Rollback

## Symptoms
Elevated HTTP 5xx error rate on `checkout-api` shortly after a new revision is deployed.

## Diagnosis
Correlate the error-rate increase with the most recent deployment. If the error rate rose
only after the new revision went live and the previous revision was healthy, the new
deployment is the likely root cause.

## Remediation
If error rate exceeds 5% within 10 minutes of a deployment, rollback to the previous stable
revision. Rolling back to the last healthy revision restores service quickly and is fully
reversible.

## Verification
Confirm the 5xx rate returns to its baseline after the rollback completes.
