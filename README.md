# Smart-Freeze — Financial Investigation Decision Support

Smart-Freeze is a prototype for reconstructing financial transaction trails, comparing fund-attribution methods, and showing where evidence is incomplete. It supports authorized human review; it does not establish guilt, create a legal lien, or freeze/release funds.

## What is real in this repository?

- **The application:** React + TypeScript + Vite frontend; FastAPI + Python backend.
- **The operational ledger included in Git:** synthetic account, transaction and case records. Dashboard values are dynamically calculated from these files, but the files are not live bank data.
- **Financial analysis:** ledger reconstruction, NetworkX transaction graph, proportional tracing, FIFO, LIBR and a method-comparison range.
- **TraceProof:** simulated Bank A, wallet and settlement adapters with evidence envelopes. These are local simulation fixtures, not live financial-institution integrations.
- **Machine learning:** a supervised classifier training pipeline is provided for the European Credit Card Fraud Detection dataset. The trained model, fresh evaluation metrics and demo test samples are generated locally and are not committed.
- **Authentication:** the default configuration disables demo authentication. Local personas are mock identities for isolated development/testing, not production authentication. OIDC/SSO/MFA are not implemented.
- **Security:** API checks, demo signing and audit telemetry are prototype controls; they have not been independently penetration-tested or certified for production use.

## Main application screens

The frontend intentionally keeps the investigator workflow to three screens:

1. **Case Overview** — live case rows, reported amounts and transaction counts returned by FastAPI.
2. **Money Flow** — a source-rooted, directed graph plus the transaction rows for the same selected case.
3. **Consensus Lien** — Proportional, FIFO and LIBR estimates for that same case, with per-account results.

The selected case is carried in the URL when moving between screens, so the graph and attribution table do not silently switch to different cases. The UI uses one local demo investigator whose visible case scope is derived from the loaded ledger. Older analysis pages are not part of the main navigation.

## Architecture

```text
React / TypeScript / Vite
        | JSON over HTTP
        v
FastAPI + Pydantic
        +-- Data validation and ledger reconstruction
        +-- Transaction graph and balance history
        +-- Proportional / FIFO / LIBR tracing
        +-- Evidence-Bounded Trace Range
        +-- Investigation priority scoring
        +-- TraceProof simulated institution adapters
        +-- ML status / inference / evaluation
        +-- Data quality and security telemetry
```

The ML classifier and deterministic tracing engine are separate. ML predictions cannot modify fund-tracing calculations or evidence verification.

## Requirements

- Python 3.11+ (3.12 recommended)
- Node.js 20+ and npm

## Run locally

### 1. Backend

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Opt in to mock identities for an isolated local demonstration only.
export SMART_FREEZE_ENV=development
export ENABLE_DEMO_AUTH=true

uvicorn app.main:app --reload
```

FastAPI docs: `http://127.0.0.1:8000/docs`

Do not use local demo identities with real financial data. If the two environment variables are not explicitly enabled in a development/test environment, protected APIs fail closed because production identity validation is not implemented.

### 2. Frontend

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open the URL printed by Vite, usually `http://localhost:5173`. The Vite configuration proxies `/api/*` to FastAPI on port 8000.

### 3. Train the ML model

Download the European Credit Card Fraud Detection dataset from its dataset page and place the original `creditcard.csv` at:

```text
data/raw/creditcard.csv
```

Then run from the repository root with the virtual environment active:

```bash
python scripts/train_ml_model.py
```

The pipeline validates the dataset, creates stratified training/validation/test partitions, fits Logistic Regression and Random Forest, selects thresholds using validation data, evaluates the held-out test partition, and writes these local artifacts:

- `models/fraud_detector_v1.joblib` — fitted Random Forest preprocessing/classification pipeline.
- `models/model_metadata.json` — metrics and metadata from that actual training run, including the artifact digest.
- `models/demo_samples.json` — labelled feature vectors from the held-out partition for interactive examples.

The source dataset and generated artifacts are ignored by Git. The API checks that the model artifact matches the recorded digest and expected feature schema. If files are missing or mismatched, model status is `UNAVAILABLE`, metrics are not shown, and prediction is disabled. The service checks for artifact-file changes when its ML endpoints are queried, so after training completes it can load the newly generated model without restarting FastAPI.

The score is an **uncalibrated positive-class score**, not a calibrated probability of fraud. The model is trained on historical European credit-card data with PCA features; it is not a model trained on Indian bank AML transactions. It does not establish guilt, trace source funds or alter the tracing range.

## Data sources and limitations

- `data/synthetic/`: controlled synthetic account-based ledger used by the operational demo.
- `data/raw/`: ignored by Git; optional public datasets must be downloaded locally.
- Elliptic: cryptocurrency transaction graph data, not an INR bank ledger.
- SynthAML alerts without `synthetic_transactions.csv`: reported as incomplete; missing companion transactions are not fabricated.
- AMLNet: inspected against the schema configured in the repository; it remains separate from the operational ledger.
- `ground_truth.json`: reserved for post-hoc synthetic tracing evaluation; it must not be exposed through operational APIs.

The Data Quality page profiles the files currently present, their observed row counts and configured schemas. “Schema valid” does not mean a dataset is integrated into tracing or that it contains real bank data.

## Tests and build

```bash
source .venv/bin/activate
pytest -q

cd frontend
npm ci
npm run build
npm run lint
```

Tests needing the optional credit-card dataset or a trained local model skip or report the model as unavailable when those artifacts are absent. The repository CI workflow runs the test suite and frontend build on pushes and pull requests.

## Main API areas

- `GET /api/health`
- `/api/auth/status`, `/api/auth/personas`, `/api/auth/demo-session`, `/api/auth/session`
- `/api/overview`, `/api/cases`, `/api/transactions`, `/api/accounts`, `/api/graph`
- `/api/consensus-lien/{case_id}`
- `/api/investigation-priority`
- `/api/data-quality`
- `/api/ml/status`, `/api/ml/evaluation`, `/api/ml/demo-samples`, `/api/ml/predict`
- `/api/traceproof/scenarios`, `/api/traceproof/start`, `/api/traceproof/requests/{request_id}`, `/api/traceproof/verify-envelope`
- `/api/admin/security-status`, `/api/admin/audit-logs`

Protected endpoints require an authenticated local demo bearer token in the explicitly opted-in development environment. Production OIDC and real-bank connectivity are not implemented.

## Production blockers

Before any real institutional use, Smart-Freeze would need a bank-approved identity provider and MFA, formal data-sharing/legal authority, partner trust/key governance, stronger deployment isolation and monitoring, independent threat-led penetration testing, and validation on authorized representative banking data. The prototype is not production-ready, and its simulated cross-institution adapters must not be presented as live integrations.
