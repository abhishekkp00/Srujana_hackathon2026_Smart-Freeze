---
trigger: always_on
---

# Smart-Freeze — Project Rules

## Project objective
Build Smart-Freeze, a transparent fraud-investigation and fund-tracing decision-support MVP for a 48-hour hackathon.

## Development workflow
1. Inspect the existing repository before making changes.
2. Implement one phase at a time.
3. Identify files to change and acceptance criteria before coding.
4. Write tests alongside implementation.
5. Run tests and inspect actual results before declaring completion.
6. Report changed files, commands executed, test outcomes, and remaining issues.
7. Do not start the next phase until the current phase passes its acceptance criteria.

## Architecture
Keep data ingestion, validation, ledger reconstruction, transaction graph, tracing algorithms, Consensus Lien, investigation scoring, evaluation, audit, and UI separate.

## Financial correctness
- Use integer paise or exact decimal arithmetic.
- Preserve transaction provenance.
- Document algorithm assumptions.
- Never silently invent or repair financial records.
- Keep proportional, FIFO, and LIBR calculations independently tested.
- Never hardcode values that should be calculated.

## Data and evaluation
- Preserve raw datasets and normalize them separately.
- Keep synthetic ground-truth labels separate from operational data.
- Never allow tracing or scoring modules to read hidden ground truth.
- Do not fabricate test results, evidence, accuracy, or benchmark metrics.
- Clearly distinguish public real-world data from synthetic data.

## Explainability and safety
- Consensus Lien reports method-dependent estimates, not legal conclusions.
- Investigation Priority Score is not a probability of guilt.
- Every displayed result must be traceable to calculations and supporting records.
- Do not implement automatic account freezes or automatic case closure.
- Consequential decisions require authorized human review.

## MVP constraints
Use Python, Pandas, NetworkX, Streamlit, Plotly, and Pytest where appropriate. Avoid unnecessary services, machine learning, LLM integration, and real-time bank integrations during the MVP.

## Completion standard
The code must be runnable, tested, reproducible, documented, and honest about limitations. Prefer a small, correct implementation over a large, unverified one.