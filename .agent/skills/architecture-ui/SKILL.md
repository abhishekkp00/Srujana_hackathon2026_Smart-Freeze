---
description: Keep Smart-Freeze modular, auditable, secure, and usable, with
  evidence-backed explanations and a functional Streamlit dashboard.
name: architecture-explainability-and-ui
---

# Smart-Freeze Architecture, Explainability and UI

## Purpose

Build a coherent Smart-Freeze application in which every displayed number
comes from the tested backend and every investigation signal is
traceable to evidence.

## Architecture rules

Keep these concerns separate: - Data loaders and dataset adapters. -
Ledger validation and balance reconstruction. - Transaction graph and
fund-flow traversal. - Proportional, FIFO, and LIBR tracing. - Consensus
Lien comparison and explanations. - Investigation Priority Score and
signals. - Ground-truth evaluation and metrics. - Audit/report
generation. - Streamlit presentation.

Inspect the repository before editing. Reuse working code, avoid
duplicate logic, and do not refactor unrelated files without a reason.
Implement one phase at a time.

## Explainability

For every tracing result or investigation score, preserve: - Input and
ledger version. - Method or scoring-rule version. - Assumptions and
warnings. - Supporting transaction IDs and evidence provenance. -
Calculation events and component breakdown. - Missing information and
uncertainty.

Generate explanations from structured calculation events and triggered
rules. Do not invent a narrative unsupported by the data.

## Investigation Priority Score

-   Keep behavioural anomalies, transaction-trail evidence, and
    historical/contextual signals separate.
-   Make weights and thresholds configurable and document that initial
    values are prototype assumptions.
-   Treat missing history as uncertainty, not proof of suspicious
    behavior.
-   Consider legitimate explanations such as payroll, marketplace
    settlement, and normal business activity.
-   Label the output as an investigation-priority score, never as a
    calibrated probability of fraud unless a proper calibration study
    has been completed.

## Dashboard

Use Streamlit and Plotly for a professional, functional interface.
Prioritize: 1. Case overview and data-quality status. 2. Interactive
transaction graph and transaction details. 3. Three-method Consensus
Lien comparison. 4. Investigation Priority Score and evidence. 5.
Evaluation results and audit/report export.

Every displayed metric must come from backend results. Never hardcode
live figures. Make filters, case selectors, links, and export controls
functional. Show loading, empty, partial-result, and error states. Keep
the interface readable, accessible, and restrained rather than adding
decorative charts.

## Security and consequential actions

-   Keep hidden evaluation labels out of operational paths.
-   Validate uploaded files and user inputs.
-   Avoid logging secrets or unnecessary sensitive data.
-   Preserve audit records for inputs, assumptions, results, and human
    review actions.
-   Do not implement unauthorized bank integrations, automatic account
    freezes, or automatic case closure.
-   Consequential decisions remain with authorized human reviewers.

## Definition of done

A task is complete only when the relevant tests pass, the UI matches
backend outputs, errors and limitations are visible, and the change is
documented.

## Completion report

List files changed, tests and commands actually run, UI behavior
verified, remaining risks, and the next smallest step.