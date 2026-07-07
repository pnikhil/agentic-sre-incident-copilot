# Aegis

Aegis is an evidence-driven, policy-gated SRE incident copilot. It takes a production alert, gathers the relevant telemetry, reasons about the likely root cause, checks the approved runbooks, and proposes a safe, reversible remediation that a human can approve. Kindly note that Aegis never makes any change on its own. The diagnosis is automated, but the remediation is always human-approved.

The larger vision is a multi-agent system running on Vertex AI Gemini, with MCP tools, grounded runbook RAG, evaluation pipelines, incident_id tracing, and a Terraform-based GCP deployment. As of now, Milestone 1 is complete and fully local.

## Platform-agnostic core, GCP as the reference deployment

Aegis is platform-agnostic in its design, and GCP-native in its reference implementation. The incident workflow core does not know about any specific cloud. It works only with provider-neutral contracts, such as ServiceRef, ResourceRef, TelemetrySummary, Evidence, RunbookMatch, Diagnosis, RemediationProposal, and RollbackTarget. All the platform-specific details live in the adapters.

A platform profile decides which adapters are wired at the composition root. Kindly find the two profiles below:

- profiles/local-fixtures.yaml, which is fully implemented and is used for all local work, the tests, and the demos.
- profiles/gcp-cloud-run.yaml, which is the reference deployment. The same is declarative for now, and its adapters (Vertex AI Gemini, Cloud Logging and Monitoring, Cloud Run, Secret Manager, Cloud Trace) will come in the later milestones.

In short, GCP, Vertex AI, and Cloud Run are simply one adapter set. The product is not trapped in a single cloud.

## Why local-first

We have deliberately built the first milestone to run entirely on your machine, with no cloud dependencies and no API keys. The reasons are quite simple:

- It keeps the cost at zero. There is no chance of any surprise cloud bill.
- It keeps development fast and deterministic. The same input gives the same result every single time.
- It lets us get the product behaviour correct first, and only later swap in the cloud pieces (Gemini, Cloud Logging, Vector Search) through the adapter layer, without rewriting the core logic.

In short, please get the local slice working correctly first. The cloud can very well come later.

## What Aegis does (Milestone 1)

Given the bad_deploy scenario, Aegis does the following:

1. Creates an incident_id for the incoming alert.
2. Summarises the raw telemetry into compact evidence items, each with its own ID. Kindly note that the raw logs are never sent to the model, only the summaries are.
3. Retrieves an approved runbook using keyword search over a local corpus.
4. Verifies that the runbook actually applies, using its applies_when and exit_when conditions.
5. Proposes a grounded rollback. The runbook quote it cites is verified to actually exist in the runbook source, so there is no scope for a made-up justification.
6. Runs a single bounded critic pass that either passes or blocks the proposal.
7. Creates an approval request in dry-run mode, carrying a payload_hash and a dry_run_hash.
8. Writes a full timeline and an artifact bundle, and prints an end-to-end result row.

## How to run

Please follow the steps below (Windows PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# run the workflow on the bad_deploy scenario
python -m aegis.cli run --scenario bad_deploy

# run the tests
pytest -q
```

## Demo app (Milestone 2)

The demoapp package is a small checkout-api that Aegis observes. It can inject a deterministic fault and emit telemetry in the very same shape that the Milestone 1 pipeline reads, so a fault toggle produces an incident that the copilot can diagnose.

```powershell
# emit a bad_deploy telemetry snapshot, and then diagnose it
python -m demoapp.cli emit --fault bad_deploy --scenario generated_bad_deploy
python -m aegis.cli run --scenario generated_bad_deploy

# optional: run the live checkout-api (needs the demo extra)
pip install -e ".[demo]"
python -m demoapp.cli serve
```

The available faults are bad_deploy and latency_spike. Kindly note that the generated scenarios are written under data/scenarios/ and are gitignored.

## Sample end-to-end result row

After a successful run, you will see a row like the one given below:

| Scenario | Runbook | Diagnosis | Action | Safety | Result | MTTR-Proposal |
|---|---|---|---|---|---|---|
| bad_deploy | checkout-bad-deploy-rollback | bad_deploy | rollback_service | Pass | Approval requested (dry-run) | 0.007s |

## Artifacts produced

For every run, Aegis writes a replay bundle under artifacts/<incident_id>/. Kindly find the contents listed below:

- incident.json, the full incident state
- evidence.json, the collected evidence
- timeline.jsonl, every state transition (this is the future trace UI and Cloud Trace story)
- diagnosis.json
- remediation_proposal.json
- policy_check.json
- approval_request.json
- e2e_result.json

A global audit log is also appended at artifacts/audit.jsonl. Please note that the artifacts folder is gitignored and can be regenerated any time.

## Architecture (ports and adapters)

The code follows a ports-and-adapters layout, so that we can start local and swap in GCP later, without touching the core logic:

- aegis/domain, the contracts (Pydantic) and the policies (priority order, grounding, invariants)
- aegis/ports, the interfaces: llm, telemetry, runbook_store, approval_store, remediation_executor, audit_log
- aegis/adapters, the local and mock implementations (Gemini and Cloud adapters will come in later milestones)
- aegis/app, the agents: triage, diagnosis, planning, critic, approval, and the workflow state machine
- data/, the deterministic scenarios and the runbook corpus
- artifacts/, the per-incident replay bundles (gitignored)

## Safety invariants

These three rules are non-negotiable:

- No Evidence, No Diagnosis.
- No Approved Runbook Quote, No Remediation Proposal.
- No Policy Pass and Valid Approval, No Write.

## Current status

Milestone 1 is green. The full bad_deploy flow works end-to-end and all the tests are passing. The next milestones will add the deterministic demo app, the real multi-agent decomposition, the MCP tools, the evaluation pipelines, and the Terraform-based GCP deployment. For any queries, please do reach out.
