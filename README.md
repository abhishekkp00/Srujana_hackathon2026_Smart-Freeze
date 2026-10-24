# Smart-Freeze

Smart-Freeze is a transparent fraud-investigation and fund-tracing decision-support MVP designed to assist authorized financial investigators in analyzing suspected fraudulent fund transfers, reconstructing transaction ledgers, tracing commingled money flows, and comparing lien estimates without automated prejudgment or black-box closures.

---

## 1. Project Purpose

When victims report cyber-fraud or unauthorized digital transactions, financial authorities and institutions must trace where the funds traveled across multi-hop accounts, identify intermediary mules, and place appropriate lien holds. 

However, blanket or arbitrary account freezes frequently harm innocent counterparties (e.g., downstream employees, legitimate merchants, or secondary recipients receiving commingled funds). Smart-Freeze addresses this challenge by providing:
- **Transparent ledger reconstruction** using exact integer arithmetic (in paise).
- **Multi-method fund tracing** comparing Proportional, FIFO, and Lowest Intermediate Balance Rule (LIBR) approaches.
- **Consensus Lien bounds** (reporting lower bounds, upper bounds, and method disagreements).
- **Evidence-backed Investigation Priority Scoring** with structured explanations.
- **Strict human-in-the-loop governance**, never implementing automated account freezes or automated case closures.

---

## 2. Current Implementation Scope

**Step 1: Project Foundation and Synthetic Data** (Complete)
- Python 3.12 project foundation with isolated core modules (`engine/`, `pipeline/`, `evaluation/`).
- Deterministic synthetic financial ledger generator (`scripts/generate_synthetic_data.py`).
- Strict schema validation adhering to integer-paise representation and explicit external counterparty conventions.
- Controlled synthetic ground truth (`data/synthetic/ground_truth.json`) stored strictly separate from operational ledger data.
- Full automated test suite in `tests/test_synthetic_data.py` with 100% pass rate.

**Step 2: Dataset Profiling, Validation and Adapters** (Complete)
- Canonical internal schemas and field definitions (`pipeline/schemas.py`).
- Structural and semantic validation engine (`pipeline/validation.py`) distinguishing fatal errors from quality warnings.
- Dataset profiling module (`pipeline/profiling.py`) producing deterministic metrics, dimensions, amounts, and distributions.
- Dataset-specific normalization adapters (`pipeline/adapters/`):
  - `SyntheticAdapter`: Operational accounts, transactions, and cases with strict ground truth isolation.
  - `EllipticAdapter`: Cryptocurrency transaction graph preserving Bitcoin UTXO edges and labels without fabricating bank accounts.
  - `SynthAMLAdapter`: SynthAML alerts adapter detecting missing companion transaction journals (`synthetic_transactions.csv`).
  - `AMLNetAdapter`: Independent multi-channel banking AML dataset adapter preserving Australian payment rails and typologies.
- Profiling CLI (`scripts/profile_datasets.py`) for human-readable and JSON reporting.
- Comprehensive test suites in `tests/test_validation.py`, `tests/test_profiling.py`, and `tests/test_adapters.py`.

**Step 3: Ledger Reconstruction and Transaction Graph** (Complete)
- Domain data models for accounts, balance events, and graph summaries (`engine/models.py`).
- Account-level running balance tracking and conservation engine (`engine/balances.py`).
- Directed multigraph construction with NetworkX preserving multiple inter-account edges and transaction provenance (`engine/transaction_graph.py`).
- End-to-end ledger reconstruction coordinator (`engine/ledger.py`) verifying global value conservation ($Opening + Deposits - Withdrawals = Final$).
- Reconstructed audit-ready balance history and graph summaries (`data/processed/`).
- CLI tool (`scripts/reconstruct_ledger.py`) for reproducible reconstruction.
- Comprehensive test suites in `tests/test_balances.py`, `tests/test_transaction_graph.py`, and `tests/test_ledger.py`.

**Step 4: Proportional Fund-Tracing Engine** (Complete)
- Tracing domain models, source pool tracking, and hop provenance (`engine/tracing_models.py`).
- Step-by-step mathematical explanation generator for proportional allocations (`engine/tracing_explanations.py`).
- Deterministic proportional fund-tracing engine (`engine/proportional.py`) tracking suspected-source lots through commingled multi-hop flows with exact integer-paise arithmetic and remainder tie-breaking.
- CLI tool (`scripts/run_proportional_trace.py`) for running tracing against designated source transactions.
- Automated test suite in `tests/test_proportional.py` verifying exact value conservation and edge-case handling.

**Step 5: FIFO Fund-Tracing Engine** (Complete)
- Deterministic First-In, First-Out (FIFO) fund-tracing engine (`engine/fifo.py`) utilizing ordered source lots.
- Structured lot lineage tracking (`FIFOLot`, `FIFOConsumptionEvent`, `FIFOAllocationExplanation`, `FIFOTraceResult` in `engine/tracing_models.py`).
- Exact integer-paise arithmetic, deterministic tie-breaking for equal timestamps, and unknown provenance preservation for incomplete account histories.
- CLI tool (`scripts/run_fifo_trace.py`) for running FIFO tracing against designated source transactions.
- Automated test suite in `tests/test_fifo.py` with 14 unit tests covering direct transfers, multi-hop propagation, partial lot consumption, commingling, withdrawals, and synthetic Case 1 validation.

**Step 6: Lowest Intermediate Balance Rule (LIBR) Fund-Tracing Engine** (Complete)
- Deterministic Lowest Intermediate Balance Rule (LIBR) fund-tracing engine (`engine/libr.py`) enforcing equitable fiduciary dissipation rules and the no-replenishment doctrine.
- Balance ceiling tracking (`LIBRAttributionEvent`, `LIBRTraceResult` in `engine/tracing_models.py`).
- Integer-paise arithmetic, clean-funds-first withdrawal dissipation, and multi-hop attribution propagation.
- CLI tool (`scripts/run_libr_trace.py`) for running LIBR tracing against designated source transactions.
- Automated test suite in `tests/test_libr.py` with 14 unit tests covering direct inflows, partial withdrawals, no-replenishment, multi-hop propagation, overdraft protection, and synthetic Case 1 validation.

**Step 7: Consensus Lien and Ground-Truth Evaluation** (Complete)
- Consensus Lien engine (`engine/consensus_lien.py`) comparing independently calculated Proportional, FIFO, and LIBR tracing results for identical source transactions, ledger cutoffs, and scopes.
- Strict integer-paise bounds: Lower Method Estimate = $\min(P, F, L)$, Upper Method Estimate = $\max(P, F, L)$, Disagreement Range = $\text{Upper} - \text{Lower}$.
- Structured, human-in-the-loop explanation generator (`engine/consensus_explanations.py`) explaining method divergence drivers, accounting conventions, incomplete history warnings, and human review requirements.
- Tracing metrics calculator (`evaluation/tracing_metrics.py`) computing exact absolute error (paise and INR), safe relative error (with explicit handling of zero ground truth), exact match rates, and scenario-grouped performance.
- Reproducible evaluation runner (`evaluation/run_tracing_evaluation.py`) benchmarking operational methods against hidden ground truth and saving reports to `data/processed/tracing_evaluation_report.json`.
- Strict operational isolation: operational tracing engines (`proportional.py`, `fifo.py`, `libr.py`, `consensus_lien.py`) never read ground truth.
- Automated test suites in `tests/test_consensus_lien.py` (10 tests) and `tests/test_tracing_evaluation.py` (6 tests).

**Step 8: Explainable Investigation Priority Scoring** (Complete)
- Behavioural feature extractor (`engine/behavioural_features.py`) measuring rapid onward fund pass-through, amount deviation relative to baseline, intermediary drain rates, graph depth, structuring/fan-out, cash withdrawal disruptions, and incomplete account history flags without reading hidden ground truth.
- Explainable priority scoring engine (`engine/investigation_score.py`) implementing the configurable prototype formula $S = 0.40B + 0.40T + 0.20H$ with evidence coverage tracking and dynamic re-normalization for missing components.
- Deterministic case ranking (`rank_cases`) with documented 4-level tie-breaking hierarchy (Score $\downarrow$, Coverage $\downarrow$, Reported Amount $\downarrow$, Case ID $\uparrow$).
- CLI tool (`scripts/run_investigation_scoring.py`) for ranking cases, generating structured narrative explanations, and exporting triage audits (`data/processed/investigation_scores.json`).
- Automated test suites in `tests/test_behavioural_features.py` (5 tests) and `tests/test_investigation_score.py` (9 tests).

**Step 9: React Frontend with FastAPI Backend** (Complete)
- **FastAPI Backend Application (`app/main.py`)**:
  - Reuses validated engines (`engine/ledger.py`, `engine/consensus_lien.py`, `engine/investigation_score.py`).
  - Strict Pydantic models for validation and responses.
  - Endpoints for overview metrics, cases, paginated/filtered transactions, account balance timelines, directed transaction graph topology, Consensus Lien multi-method comparisons, and data quality audits.
  - Ground-truth isolation: operational endpoints cannot access `ground_truth.json`.
  - Comprehensive API test suite in `tests/test_api.py` (11 tests).
- **React Frontend Application (`frontend/`)**:
  - Built with React 18, Vite, TypeScript, and Tailwind CSS.
  - Interactive directed multigraph visualization powered by Cytoscape.js.
  - Chronological account balance timelines rendered via Recharts.
  - Five core investigation views (Overview, Transaction Explorer, Consensus Lien, Investigation Review, Data Quality).

**Step 10: Machine Learning Fraud Classifier on European Credit Card Benchmark** (Complete)
- Genuine transaction-fraud classification model trained on the ULB / Worldline European Credit Card dataset (284,807 transactions, 492 fraud cases, 0.173% class imbalance).
- Random Forest primary candidate achieving **87.50% Precision**, **75.68% Recall**, **0.8116 F1-score**, and **0.8079 PR-AUC** on held-out test data (42,722 transactions).
- Operating threshold ($\tau = 0.63$) selected strictly on validation data to optimize minority F1-score.
- Dedicated interactive ML Analysis dashboard with live feature inspector and real test demo vectors.
- Automated test suite in `tests/test_ml.py` (15 tests).

**Step 12: TraceProof Multi-Rail Evidence Reconstruction** (Complete)
- Core capability reconstructing verifiable transaction trails across three independent institutions:
  1. **Bank A**: Originating retail/commercial banking rail.
  2. **Wallet B**: PPI / e-money digital wallet provider.
  3. **Bank C / Settlement Provider**: Acquiring bank and merchant settlement clearing processor.
- **Signed Evidence Envelopes**: Ed25519 digital signatures and SHA-256 canonical payload hashing ensuring envelope authenticity and payload integrity against an institutional public-key registry.
- **Strict Evidence Standards**: Distinguishes **CONFIRMED**, **INFERRED**, **AMBIGUOUS**, **CONTRADICTORY**, and **UNRESOLVED** links. Missing counterparty records remain visibly unresolved and are never silently fabricated.
- **Evidence-Bounded Trace Range**: Integrates multi-method bounds (Proportional, FIFO, LIBR) calculated across verified evidence hops.
- **Trace Coordinator & Scenarios**: Complete cross-institution trail, unresolved settlement gap, fee/refund tracking, and adversarial tampered envelope detection.
- Automated test suite in `tests/test_traceproof.py` (11 tests).

---

## 3. Folder Structure

```text
smart-freeze/
├── .gitignore                          # Git exclusions for Python caches, venvs, and temp files
├── README.md                           # Project documentation, schemas, and usage guide
├── requirements.txt                    # Production and testing dependencies (FastAPI, uvicorn, pydantic, etc.)
├── app/                                # FastAPI backend service
│   ├── __init__.py
│   └── main.py                         # FastAPI application entrypoint and REST endpoints
├── frontend/                           # React + Vite + TypeScript frontend
│   ├── package.json                    # Frontend dependencies (React, Vite, Recharts, Cytoscape, Lucide)
│   ├── vite.config.ts                  # Vite configuration with /api backend proxy
│   ├── tailwind.config.js              # Tailwind CSS styling tokens (Navy, Slate, Teal)
│   └── src/
│       ├── main.tsx                    # React application entrypoint
│       ├── App.tsx                     # React Router navigation and layout shell
│       ├── api/                        # Centralized Axios API client and endpoint functions
│       ├── components/                 # Reusable UI components (Sidebar, Navbar, StatCard, Badge)
│       ├── pages/                      # 5 investigation views (Overview, TransactionExplorer, etc.)
│       └── types/                      # TypeScript domain types and API contracts
├── data/
│   ├── raw/                            # Immutable external datasets (e.g., AMLNet, Elliptic, SynthAML)
│   ├── processed/                      # Normalized operational data
│   │   ├── balance_history.csv         # Reconstructed account balance event histories
│   │   ├── ledger_validation_report.json # Conservation and data validation audit
│   │   └── transaction_graph_summary.json # Topological graph statistics
│   └── synthetic/                      # Generated deterministic benchmark dataset
│       ├── accounts.csv                # Operational account ledger
│       ├── transactions.csv            # Operational chronological transaction journal
│       ├── cases.csv                   # Reported fraud cases
│       └── ground_truth.json           # Evaluation-only hidden ground truth (isolated)
├── engine/                             # Core algorithms package (ledger, balances, graph, tracing)
│   ├── __init__.py
│   ├── models.py                       # Ledger domain models and event representations
│   ├── balances.py                     # Account running balance tracking and conservation
│   ├── transaction_graph.py            # NetworkX MultiDiGraph constructor and summary
│   ├── ledger.py                       # End-to-end ledger reconstruction coordinator
│   ├── tracing_models.py               # Source pool models, FIFO lots, and structured trace results
│   ├── tracing_explanations.py         # Step-by-step mathematical allocation explanation builder
│   ├── proportional.py                 # Deterministic proportional fund-tracing engine
│   ├── fifo.py                         # Deterministic FIFO fund-tracing engine
│   ├── libr.py                         # Deterministic Lowest Intermediate Balance Rule (LIBR) engine
│   ├── consensus_lien.py               # Consensus Lien comparison engine (min/max bounds, disagreement)
│   ├── consensus_explanations.py       # Narrative and accounting divergence explanation builder
│   ├── behavioural_features.py         # Multi-hop trail and behavioural feature extractor
│   └── investigation_score.py          # Explainable Investigation Priority Scoring engine
├── pipeline/                           # Data ingestion, schema validation, profiling, and adapters
│   ├── __init__.py
│   ├── schemas.py                      # Canonical schemas and field specifications
│   ├── validation.py                   # Structural and semantic data validation
│   ├── profiling.py                    # Deterministic profiling and statistical metrics
│   └── adapters/                       # Dataset-specific adapters
│       ├── __init__.py
│       ├── synthetic_adapter.py        # Operational Smart-Freeze synthetic ledger adapter
│       ├── elliptic_adapter.py         # Elliptic Bitcoin cryptocurrency graph adapter
│       └── synthaml_adapter.py         # SynthAML and AMLNet dataset adapters
├── evaluation/                         # Ground-truth evaluation and benchmark comparison modules
│   ├── __init__.py
│   ├── tracing_metrics.py              # Error metrics (paise, INR, relative error, match rate)
│   └── run_tracing_evaluation.py       # Benchmark evaluation runner reading ground truth
├── scripts/
│   ├── generate_synthetic_data.py      # Deterministic synthetic data generation script
│   ├── profile_datasets.py             # CLI tool for dataset profiling and validation
│   ├── reconstruct_ledger.py           # CLI tool for ledger reconstruction and graph generation
│   ├── run_proportional_trace.py       # CLI tool for executing proportional fund tracing
│   ├── run_fifo_trace.py               # CLI tool for executing FIFO fund tracing
│   ├── run_libr_trace.py               # CLI tool for executing LIBR fund tracing
│   └── run_investigation_scoring.py    # CLI tool for priority scoring and case triage
└── tests/
    ├── test_synthetic_data.py          # Step 1 synthetic data validation tests
    ├── test_validation.py              # Step 2 structural validation tests
    ├── test_profiling.py               # Step 2 profiling tests
    ├── test_adapters.py                # Step 2 dataset adapter tests
    ├── test_balances.py                # Step 3 balance tracking tests
    ├── test_transaction_graph.py       # Step 3 transaction graph tests
    ├── test_ledger.py                  # Step 3 ledger reconstruction tests
    ├── test_proportional.py            # Step 4 proportional tracing tests
    ├── test_fifo.py                    # Step 5 FIFO fund-tracing tests
    ├── test_libr.py                    # Step 6 LIBR fund-tracing tests
    ├── test_consensus_lien.py          # Step 7 Consensus Lien tests
    ├── test_tracing_evaluation.py      # Step 7 Ground-truth evaluation tests
    ├── test_behavioural_features.py    # Step 8 Behavioural feature extraction tests
    └── test_investigation_score.py     # Step 8 Investigation Priority Scoring tests

```


---

## 4. Environment Setup and Run Commands

### Prerequisites
- Python 3.11 or later (tested on Python 3.12.3)

### Installation
Install minimal dependencies:
```bash
pip install -r requirements.txt
```

### Generating Synthetic Data
Generate the deterministic dataset using the standard random seed:
```bash
python3 scripts/generate_synthetic_data.py --seed 42 --output-dir data/synthetic
```

### Profiling Datasets
Run the dataset profiling and validation tool:
```bash
# Profile the synthetic dataset
python3 scripts/profile_datasets.py --dataset synthetic

# Profile all available datasets (synthetic, Elliptic, SynthAML alerts, AMLNet)
python3 scripts/profile_datasets.py --dataset all

# Output profile report in JSON format
python3 scripts/profile_datasets.py --dataset synthetic --json
```

### Ledger Reconstruction & Transaction Graph
Reconstruct chronological account balance histories and generate the transaction graph:
```bash
python3 scripts/reconstruct_ledger.py
```
This generates audit-ready artifacts in `data/processed/`:
- `data/processed/balance_history.csv`
- `data/processed/ledger_validation_report.json`
- `data/processed/transaction_graph_summary.json`

### Proportional Fund Tracing
Execute deterministic proportional fund tracing from a designated source transaction:
```bash
# Trace Case 1 suspected fraud origin (TXN_0009)
python3 scripts/run_proportional_trace.py --tx-id TXN_0009 --case-id CASE-2026-001

# Trace with verbose mathematical allocation explanations
python3 scripts/run_proportional_trace.py --tx-id TXN_0009 --verbose
```

### FIFO & LIBR Fund Tracing
```bash
# Run FIFO tracing
python3 scripts/run_fifo_trace.py --tx-id TXN_0009 --case-id CASE-2026-001 --verbose

# Run LIBR tracing
python3 scripts/run_libr_trace.py --tx-id TXN_0009 --case-id CASE-2026-001 --verbose
```

### Ground-Truth Tracing Evaluation Runner
Run the evaluation runner to benchmark all tracing algorithms and Consensus Lien against hidden ground truth:
```bash
python3 evaluation/run_tracing_evaluation.py --output data/processed/tracing_evaluation_report.json
```

### Explainable Investigation Priority Scoring CLI
Score and rank cases for authorized human triage, generating structured explanations:
```bash
# Rank all cases in the synthetic ledger
python3 scripts/run_investigation_scoring.py

# Score a specific case with detailed evidence provenance
python3 scripts/run_investigation_scoring.py --case-id CASE-2026-001 --verbose

# Export triage rankings to JSON
python3 scripts/run_investigation_scoring.py --output data/processed/investigation_scores.json
```

### Running Tests
Execute the full automated test suite:
```bash
pytest -v
```

### Running the App (Placeholder)
```bash
streamlit run app.py
```

---

## 5. Synthetic Data Schemas

All operational financial amounts are stored as **positive integer paise** (1 INR = 100 paise; e.g., ₹1,000.00 = `100000` paise). Binary floating-point currency representation is strictly prohibited.

### `accounts.csv`
| Column | Type | Description |
| :--- | :--- | :--- |
| `account_id` | String | Unique account identifier (`ACC_...`) |
| `account_type` | String | Account classification (`savings`, `current`, `corporate`, `merchant`, `salary`) |
| `opening_balance_paise` | Integer | Initial account balance in paise ($\ge 0$) |
| `history_complete` | Boolean | `True` if historical statements are complete; `False` if incomplete or truncated |

### `transactions.csv`
| Column | Type | Description |
| :--- | :--- | :--- |
| `transaction_id` | String | Unique transaction identifier (`TXN_0001` ..) |
| `timestamp` | String | ISO 8601 UTC timestamp (`YYYY-MM-DDTHH:MM:SSZ`) |
| `from_account` | String | Originating internal account (`ACC_...`) or external counterparty (`EXT_...`) |
| `to_account` | String | Destination internal account (`ACC_...`) or external counterparty (`EXT_...`) |
| `amount_paise` | Integer | Transaction amount in paise ($> 0$) |
| `transaction_type` | String | Operation type (`transfer`, `deposit`, `withdrawal`, `salary_credit`, `merchant_payment`) |
| `case_id` | String | Associated fraud case ID (`CASE-YYYY-NNN`) or empty (`""`) if unrelated |
| `evidence_status` | String | Provenance label (`suspected_fraud`, `verified_legitimate`, etc.) |

### `cases.csv`
| Column | Type | Description |
| :--- | :--- | :--- |
| `case_id` | String | Unique case identifier (`CASE-2026-001` ..) |
| `reported_date` | String | Date and time complaint was lodged (ISO 8601) |
| `reported_amount_paise` | Integer | Total disputed loss amount in paise ($> 0$) |
| `status` | String | Case disposition (`under_investigation`, `open`, etc.) |

### External Counterparty Convention
Boundary entities outside the closed financial ledger are prefixed with `EXT_` (e.g., `EXT_CASH_ATM`, `EXT_CLIENT_PAYMENT`, `EXT_UTILITY_GATEWAY`, `EXT_SUPPLIER_WHOLESALE`). Transactions between two external counterparties are invalid; at least one side must be an internal ledger account.

---

## 6. Deterministic Generation & Ground-Truth Isolation

### Determinism
The generator uses a seedable Pseudo-Random Number Generator (`random.Random(seed)`) and deterministic timestamp-based sorting. Generating with the same seed guarantees 100% byte-for-byte identical output across platforms.

### Ground-Truth Isolation
`ground_truth.json` contains:
- Controlled source-lot lineage (origin transactions, lot IDs, initial amounts).
- Known per-account allocations (retained vs. forwarded suspected funds).
- Exact transaction ground-truth classifications.
- Mapping of all seven required scenarios:
  1. Ordinary salary & everyday business activity.
  2. Suspected source inflow followed by direct onward transfer.
  3. Split transfers across multiple accounts (fan-out / smurfing).
  4. Commingling of suspected and legitimate funds.
  5. Partial withdrawals leaving remaining balances.
  6. Legitimate merchant receiving payments from multiple customers.
  7. Account with incomplete historical statement records.

> **CRITICAL RULE**: Operational tracing engines (FIFO, Proportional, LIBR) and scoring modules must **never** read `ground_truth.json`. It is strictly reserved for post-hoc benchmark evaluation modules in `evaluation/`.

---

## 7. Supported Dataset Adapters & Optional Datasets

| Dataset | Location | Status | Notes / Limitations |
| :--- | :--- | :--- | :--- |
| **Smart-Freeze Synthetic** | `data/synthetic/` | Supported | Internal operational ledger in integer paise (`accounts.csv`, `transactions.csv`, `cases.csv`). Ground truth strictly isolated. |
| **Elliptic Bitcoin** | `data/raw/elliptic_bitcoin_dataset/` | Supported | Cryptocurrency transaction graph (`elliptic_txs_classes.csv`, `elliptic_txs_edgelist.csv`, `elliptic_txs_features.csv`). Labels: illicit (1), licit (2), unknown. Preserves directed UTXO flows; does NOT represent bank accounts or INR balances. |
| **SynthAML Alerts** | `data/raw/synthetic_alerts.csv` | Partially Supported (Orphan) | Contains 20,000 alerts with Outcome (`Report`, `Dismiss`). Companion `synthetic_transactions.csv` is missing from `data/raw/`. Retained as orphan alerts; companion is not fabricated. |
| **AMLNet** | `data/raw/AMLNet_August 2025.csv` | Supported (Separate) | Australian multi-channel banking transaction dataset (1.09M rows) with 17 features including typologies (`structuring`, `layering`, `integration`). Treated as independent dataset; NOT conflated with SynthAML. |
| **European Credit Card Fraud** | `data/raw/creditcard.csv` | Supported (Real Historical) | ULB / Worldline benchmark (284,807 transactions, 492 fraud cases, 0.173% fraud rate) with PCA features `V1`–`V28`, `Time`, and `Amount`. Used strictly for isolated ML transaction fraud classification. |

### Supplying Optional Public Datasets
- **European Credit Card Fraud**: Place `creditcard.csv` in `data/raw/` (or download via Kaggle: `https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud`).
- **Elliptic**: Place `elliptic_txs_classes.csv`, `elliptic_txs_edgelist.csv`, and optionally `elliptic_txs_features.csv` in `data/raw/elliptic_bitcoin_dataset/`.
- **SynthAML**: Place `synthetic_alerts.csv` and `synthetic_transactions.csv` in `data/raw/`.
- **AMLNet**: Place `AMLNet_August 2025.csv` in `data/raw/`.

Raw datasets remain immutable under `data/raw/` and are never committed if exceeding repository limits.

---

## 8. Machine Learning Transaction Fraud Classifier

### Dataset Provenance
- Source: European Credit Card Fraud Detection (ULB Machine Learning Group & Worldline, Kaggle).
- Dimensions: 284,807 rows, 30 features (`Time`, `V1`..`V28`, `Amount`), target `Class` (492 fraud cases, 0.173% class imbalance).
- Splitting: Stratified 70% Train (199,364 rows), 15% Validation (42,721 rows), and 15% Held-Out Test (42,722 rows) with fixed random seed (`42`). The test set is strictly held out.
- Preprocessing: `RobustScaler` fitted strictly on training data for `Time` and `Amount`; PCA features passed through. Target weighting applied strictly in training.

### Model Comparison & Held-Out Test Metrics
Operating threshold selected on validation data ($\tau = 0.63$) to optimize F1 score for minority fraud class:

| Model | Operating Threshold | Precision | Recall | F1-Score | PR-AUC | ROC-AUC | Accuracy (Suppl.) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Random Forest (Primary)** | **0.63** | **87.50%** | **75.68%** | **0.8116** | **0.8079** | **0.9706** | **99.94%** |
| Logistic Regression (Baseline) | 0.95 | 42.76% | 83.78% | 0.5662 | 0.7923 | 0.9677 | 99.88% |

- **Held-Out Confusion Matrix (Random Forest on 42,722 test samples)**:
  - True Positives (TP): 56
  - False Positives (FP): 8 (False positive rate: 0.019%)
  - False Negatives (FN): 18
  - True Negatives (TN): 42,640

### Training CLI Command
```bash
python scripts/train_ml_model.py
```
Outputs versioned pipeline `models/fraud_detector_v1.joblib`, evaluation report `models/model_metadata.json`, and 10 real demo samples `models/demo_samples.json`.

### ML Endpoints
- `GET /api/ml/status` — Model load status, version, operating threshold, and feature schema.
- `GET /api/ml/evaluation` — Full held-out test evaluation report comparing Random Forest and Baseline Logistic Regression.
- `GET /api/ml/demo-samples` — Verified real test samples for interactive UI prediction demos.
- `POST /api/ml/predict` — Evaluates fraud risk score for a 30-dimensional feature vector, returning score, threshold, predicted label, and governance disclaimer.

### Architectural Boundary & Governance
- **Strict Isolation**: The ML classifier evaluates credit card PCA features and operates as an independent transaction fraud risk signal.
- **No Alteration of Tracing**: It does NOT alter or influence Proportional tracing, FIFO tracing, LIBR tracing, or Consensus Lien recovery estimates.
- **Decision Support**: The output is an uncalibrated heuristic risk score and does NOT constitute legal proof of guilt or automatic account freeze justification.

---

## 8. Known Limitations

- **Synthetic Domain**: These records are generated for algorithmic testing and decision-support validation; they do not represent real proprietary banking data.
- **Simplified Counterparties**: Real inter-bank settlements involve clearing houses, payment aggregators, and chargeback lifecycles which are abstracted via `EXT_` counterparties in this synthetic ledger.
- **SynthAML Companion Absence**: `synthetic_transactions.csv` is missing in `data/raw/`, so `synthetic_alerts.csv` cannot be joined to transaction logs.

---

## 9. Launch Instructions (FastAPI & React)

### Prerequisites
- Python 3.12+ with virtual environment configured (`.venv`).
- Node.js 18+ and npm.

### Backend (FastAPI)
To run the FastAPI server:
```bash
# From workspace root
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
API docs are interactively available at: `http://127.0.0.1:8000/docs`

### Frontend (React + Vite)
To start the React development server:
```bash
# Navigate to frontend/ directory
cd frontend
npm install
npm run dev
```
The application will be available at `http://localhost:5173`. Vite is pre-configured to proxy `/api/*` requests to the FastAPI backend at `http://localhost:8000`.

To create a production build:
```bash
cd frontend
npm run build
```

### Running Test Suites
```bash
# Run all backend unit, integration, and API tests
.venv/bin/pytest -v
```
- **Step 4 Boundary**: FIFO and LIBR tracing algorithms, Consensus Lien bounds, and investigation scoring will be implemented in Step 5. Proportional tracing estimates reflect algorithm assumptions (fungible commingling) and do not constitute legal conclusions or proof of guilt.

