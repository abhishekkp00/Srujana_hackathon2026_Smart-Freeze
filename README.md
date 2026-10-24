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

*Upcoming Phases:*
- **Step 6:** Lowest Intermediate Balance Rule (LIBR), Consensus Lien comparison, Investigation Scoring, and Streamlit Dashboard.

---

## 3. Folder Structure

```text
smart-freeze/
├── .gitignore                          # Git exclusions for Python caches, venvs, and temp files
├── README.md                           # Project documentation, schemas, and usage guide
├── requirements.txt                    # Minimal production and testing dependencies
├── app.py                              # Streamlit dashboard entrypoint (Step 1 placeholder)
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
│   └── fifo.py                         # Deterministic FIFO fund-tracing engine
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
├── evaluation/                         # Evaluation metrics and benchmark comparison modules
│   └── __init__.py
├── scripts/
│   ├── generate_synthetic_data.py      # Deterministic synthetic data generation script
│   ├── profile_datasets.py             # CLI tool for dataset profiling and validation
│   ├── reconstruct_ledger.py           # CLI tool for ledger reconstruction and graph generation
│   ├── run_proportional_trace.py       # CLI tool for executing proportional fund tracing
│   └── run_fifo_trace.py               # CLI tool for executing FIFO fund tracing
└── tests/
    ├── test_synthetic_data.py          # Step 1 synthetic data validation tests
    ├── test_validation.py              # Step 2 structural validation tests
    ├── test_profiling.py               # Step 2 profiling tests
    ├── test_adapters.py                # Step 2 dataset adapter tests
    ├── test_balances.py                # Step 3 balance tracking tests
    ├── test_transaction_graph.py       # Step 3 transaction graph tests
    ├── test_ledger.py                  # Step 3 ledger reconstruction tests
    ├── test_proportional.py            # Step 4 proportional tracing tests
    └── test_fifo.py                    # Step 5 FIFO fund-tracing tests
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

### Supplying Optional Public Datasets
- **Elliptic**: Place `elliptic_txs_classes.csv`, `elliptic_txs_edgelist.csv`, and optionally `elliptic_txs_features.csv` in `data/raw/elliptic_bitcoin_dataset/`.
- **SynthAML**: Place `synthetic_alerts.csv` and `synthetic_transactions.csv` in `data/raw/`.
- **AMLNet**: Place `AMLNet_August 2025.csv` in `data/raw/`.

Raw datasets remain immutable under `data/raw/` and are never committed if exceeding repository limits.

---

## 8. Known Limitations

- **Synthetic Domain**: These records are generated for algorithmic testing and decision-support validation; they do not represent real proprietary banking data.
- **Simplified Counterparties**: Real inter-bank settlements involve clearing houses, payment aggregators, and chargeback lifecycles which are abstracted via `EXT_` counterparties in this synthetic ledger.
- **SynthAML Companion Absence**: `synthetic_transactions.csv` is missing in `data/raw/`, so `synthetic_alerts.csv` cannot be joined to transaction logs.
- **Step 4 Boundary**: FIFO and LIBR tracing algorithms, Consensus Lien bounds, and investigation scoring will be implemented in Step 5. Proportional tracing estimates reflect algorithm assumptions (fungible commingling) and do not constitute legal conclusions or proof of guilt.

