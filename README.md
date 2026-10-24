# FairHold

FairHold is a transparent fraud-investigation and fund-tracing decision-support MVP designed to assist authorized financial investigators in analyzing suspected fraudulent fund transfers, reconstructing transaction ledgers, tracing commingled money flows, and comparing lien estimates without automated prejudgment or black-box closures.

---

## 1. Project Purpose

When victims report cyber-fraud or unauthorized digital transactions, financial authorities and institutions must trace where the funds traveled across multi-hop accounts, identify intermediary mules, and place appropriate lien holds. 

However, blanket or arbitrary account freezes frequently harm innocent counterparties (e.g., downstream employees, legitimate merchants, or secondary recipients receiving commingled funds). FairHold addresses this challenge by providing:
- **Transparent ledger reconstruction** using exact integer arithmetic (in paise).
- **Multi-method fund tracing** comparing Proportional, FIFO, and Lowest Intermediate Balance Rule (LIBR) approaches.
- **Consensus Lien bounds** (reporting lower bounds, upper bounds, and method disagreements).
- **Evidence-backed Investigation Priority Scoring** with structured explanations.
- **Strict human-in-the-loop governance**, never implementing automated account freezes or automated case closures.

---

## 2. Current Implementation Scope (Step 1)

**Step 1: Project Foundation and Synthetic Data** (Complete)
- Python 3.12 project foundation with isolated core modules (`engine/`, `pipeline/`, `evaluation/`).
- Deterministic synthetic financial ledger generator (`scripts/generate_synthetic_data.py`).
- Strict schema validation adhering to integer-paise representation and explicit external counterparty conventions.
- Controlled synthetic ground truth (`data/synthetic/ground_truth.json`) stored strictly separate from operational ledger data.
- Full automated test suite in `tests/test_synthetic_data.py` with 100% pass rate.
- Minimal placeholder dashboard (`app.py`).

*Upcoming Phases:*
- **Step 2:** Ingestion pipeline and balance conservation / ledger reconstruction.
- **Step 3:** Transaction graph representation and independent tracing algorithms (FIFO, Proportional, LIBR).
- **Step 4:** Consensus Lien and Investigation Priority Scoring.
- **Step 5:** Interactive Streamlit Dashboard and Audit Reporting.

---

## 3. Folder Structure

```text
fairhold/
├── .gitignore                          # Git exclusions for Python caches, venvs, and temp files
├── README.md                           # Project documentation, schemas, and usage guide
├── requirements.txt                    # Minimal production and testing dependencies
├── app.py                              # Streamlit dashboard entrypoint (Step 1 placeholder)
├── data/
│   ├── raw/                            # Immutable external datasets (e.g., AML, Elliptic)
│   ├── processed/                      # Normalized operational data
│   └── synthetic/                      # Generated deterministic benchmark dataset
│       ├── accounts.csv                # Operational account ledger
│       ├── transactions.csv            # Operational chronological transaction journal
│       ├── cases.csv                   # Reported fraud cases
│       └── ground_truth.json           # Evaluation-only hidden ground truth (isolated)
├── engine/                             # Core algorithms package (ledger, tracing, lien, scoring)
│   └── __init__.py
├── pipeline/                           # Data ingestion, schema validation, and normalization
│   └── __init__.py
├── evaluation/                         # Evaluation metrics and benchmark comparison modules
│   └── __init__.py
├── scripts/
│   └── generate_synthetic_data.py      # Deterministic synthetic data generation script
└── tests/
    └── test_synthetic_data.py          # Pytest validation test suite
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

## 7. Known Limitations

- **Synthetic Domain**: These records are generated for algorithmic testing and decision-support validation; they do not represent real proprietary banking data.
- **Simplified Counterparties**: Real inter-bank settlements involve clearing houses, payment aggregators, and chargeback lifecycles which are abstracted via `EXT_` counterparties in this synthetic ledger.
- **Step 1 Boundary**: Tracing algorithms, graph traversal, and UI visualization will be introduced in subsequent steps.
