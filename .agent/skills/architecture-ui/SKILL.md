---
description: Keep Smart-Freeze modular, auditable, secure, and usable with evidence-backed explanations and a data-driven React interface.
name: architecture-explainability-and-ui
---

# Smart-Freeze Architecture, Explainability and UI

## Purpose
Build one coherent Smart-Freeze application. The backend is FastAPI; the frontend is React + TypeScript. Do not add a Streamlit dashboard or duplicate UI entry point.

## Architecture rules
Keep separate: dataset adapters, validation, ledger reconstruction, transaction graph, proportional/FIFO/LIBR tracing, Evidence-Bounded Trace Range, investigation prioritization, ML training/inference, TraceProof signatures, audit, API and UI.

Inspect the repository before editing. Reuse tested code, avoid duplicate logic, and change one concern at a time.

## Explainability
For every tracing or scoring result preserve source references, dataset/ledger context, algorithm or model version, assumptions, data-quality warnings, calculation details and uncertainty. Explanations must come from structured calculation results—not invented prose.

## Investigation priority
- Keep behavioural anomalies, transaction-trail evidence and historical/contextual signals separate.
- Weights and thresholds are prototype assumptions unless calibrated and validated.
- Missing history is uncertainty, not a low-risk signal.
- The score is investigation priority, not probability of fraud.

## React interface
Use the existing React, TypeScript, Vite and Tailwind stack. Use Recharts for supported numerical charts and Cytoscape.js for transaction graphs where already configured.

Every displayed metric must come from a backend response, a verified local file, or a calculation. Never hardcode live case rows, counts, recent activity, model metrics or service health. Static synthetic examples are allowed only when clearly labelled as fixtures/simulated institution data.

Implement clear loading, empty, partial-result, unavailable, and error states. Filters, case selectors, trace actions and prediction controls must operate on API responses.

## Security and consequential actions
- Keep hidden evaluation labels out of operational endpoints.
- Validate requests and source evidence.
- Do not expose secrets or unnecessary sensitive records.
- Do not claim production authentication, immutable audit logs, or real-bank connections unless they exist and are verified.
- No automatic account freezes or case closure.

## Definition of done
Relevant tests pass, the frontend build succeeds, displayed outputs match backend results, and remaining limitations are visible.

## Completion report
List changed files, commands actually run, test/build outputs, behaviour verified, remaining risks and exact next steps.
