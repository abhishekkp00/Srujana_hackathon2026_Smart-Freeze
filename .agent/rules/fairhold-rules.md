---
trigger: always_on
---

# FairHold — Project Rules

## Project objective
Build FairHold, an evidence-first financial investigation and fund-tracing decision-support MVP. The stack is FastAPI + Python on the backend and React + TypeScript on the frontend. Do not introduce Streamlit or a second web application.

## Development workflow
1. Inspect the existing repository before changing code.
2. Implement one bounded change at a time.
3. Identify acceptance criteria and affected files before coding.
4. Add or update tests with the implementation.
5. Run checks and inspect actual output before claiming success.
6. Report changed files, commands executed, test outcomes, and remaining issues.
7. Do not add demo values to production-facing views to conceal missing data or service failures.

## Architecture
Keep data ingestion, validation, ledger reconstruction, transaction graph, tracing algorithms, ML training/inference, TraceProof evidence verification, investigation scoring, evaluation, audit, API and React UI separate.

## Financial correctness
- Use integer minor units or exact decimal arithmetic.
- Preserve transaction provenance and event relationships.
- Document algorithm assumptions and method comparability.
- Never silently invent, repair, or double-count financial records.
- Keep proportional, FIFO, and LIBR calculations independently tested.
- Unknown amounts, balances, history and evidence links must remain unavailable/unknown, not be replaced with zero.

## Data and ML evaluation
- Preserve raw datasets and normalize into separate processed outputs.
- Keep synthetic ground-truth labels separate from operational inputs.
- Do not expose hidden ground truth through operational APIs.
- Do not fabricate model metrics, training status, data counts or predictions.
- Derive displayed metrics from APIs, local files, model metadata or actual calculations.
- Clearly distinguish historical credit-card fraud data, cryptocurrency graphs, synthetic banking scenarios and real banking data.
- A model artifact is usable only after schema and recorded-digest validation.

## Security and explainability
- Enforce access control in FastAPI, never only in React.
- Never silently select an admin identity or expose demo tokens in the UI.
- Label local persona authentication as mock demonstration authentication.
- Do not claim production OIDC, immutable logs, penetration testing or a globally secure system unless implemented and verified.
- Consensus Lien / Evidence-Bounded Trace Range reports method-dependent estimates, not legal conclusions.
- Investigation Priority Score is not a probability of guilt.
- Do not implement automatic account freezes, fund release or case closure.
- Consequential decisions remain with authorized human reviewers.

## MVP constraints
Use FastAPI, Pydantic, pandas, NetworkX, scikit-learn, Pytest, React, TypeScript, Vite, Tailwind CSS and the existing chart/graph libraries where they are already used. External institutions are simulated; never claim live bank integration.

## Completion standard
Prefer a small, correct, dynamically data-driven implementation over a large, unverified one. Every data panel must have clear loading, unavailable, empty and error states. The project must remain runnable, reproducible, documented, and honest about limitations.
