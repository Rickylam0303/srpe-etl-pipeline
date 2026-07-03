# SRPE Residential Sales ETL Pipeline

End-to-end ETL pipeline that ingests **Hong Kong SRPE** (一手住宅物業銷售資訊網) Register of Transactions PDFs, cleans bilingual transaction data, loads a PostgreSQL star schema, and prepares SQL views for analytics dashboards.

> **v1 (current):** Extract → Transform → Load — production pipeline complete  
> **v2 (planned):** Excel + Power Query dashboard on top of PostgreSQL views

---

## Why this project?

Hong Kong pre-sale residential transaction data is published as **large bilingual PDFs** per development. This project automates:

- Downloading RT PDFs from the official SRPE website
- Parsing tabular transaction records (columns A–H)
- Normalizing prices, dates, payment terms, and transaction status (including 撻訂 / amendments)
- Loading a **star schema** in PostgreSQL with **UPSERT** semantics for data refreshes

Sample development: **THE PAVILIA FARM III (柏傲莊 III)** — 706-page PDF, **1,145 transactions**.

---

## Architecture

```
SRPE Website / Local PDF
        │
        ▼
┌─────────────────┐
│  Extract        │  pdfplumber + Playwright + SQLite ingestion log
│  run_extract.py │
└────────┬────────┘
         │  staging CSV
         ▼
┌─────────────────┐
│  Transform      │  Pandas — dates, HKD prices, payment mapping, natural keys
│  run_transform.py
└────────┬────────┘
         │  clean CSV
         ▼
┌─────────────────┐
│  Load           │  PostgreSQL star schema + UPSERT
│  run_load.py    │
└────────┬────────┘
         │
         ▼
   PostgreSQL (srpe_etl)
   dim_development │ dim_property │ dim_payment_term │ fact_sales
         │
         ▼ (v2)
   Excel Power Query → vw_sales_detail
```

---

## Tech stack

| Layer | Tools |
|-------|-------|
| Extract | Python, pdfplumber, Playwright, httpx, SQLite |
| Transform | pandas |
| Load | PostgreSQL 18, psycopg3, star schema |
| Visualize (v2) | Excel Power Query, SQL views |
| Config | YAML, `.env` (secrets) |

---

## Project structure

```
├── run_extract.py          # CLI: local PDF or SRPE download
├── run_transform.py        # Clean staging → transformed CSV
├── run_load.py             # Init DB / schema / views / UPSERT load
├── extract/                # PDF parser, SRPE client, ingestion log
├── transform/              # Cleaners, bilingual payment mapper
├── load/                   # schema.sql, views.sql, loader
└── config/settings.yaml    # Non-secret paths & settings
```

---

## Quick start

### 1. Prerequisites

- Python 3.11+
- PostgreSQL 14+ (tested on PostgreSQL 18)
- Playwright browsers (for SRPE download mode)

### 2. Install

```powershell
cd "ETL Pipeline"
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\playwright install chromium
```

### 3. Configure database

```powershell
copy .env.example .env
# Edit .env — set SRPE_DB_PASSWORD to your postgres password
```

Create database, schema, views, and load data:

```powershell
.\.venv\Scripts\python run_load.py --create-db --init-db --init-views
.\.venv\Scripts\python run_load.py
```

### 4. Run the pipeline

**Option A — local PDF (no network scrape):**

```powershell
.\.venv\Scripts\python run_extract.py local --pdf "path\to\64048260626081RT.pdf"
.\.venv\Scripts\python run_transform.py
.\.venv\Scripts\python run_load.py
```

**Option B — download from SRPE:**

```powershell
.\.venv\Scripts\python run_extract.py srpe --dev-id 7705
.\.venv\Scripts\python run_transform.py
.\.venv\Scripts\python run_load.py
```

---

## Data model

Star schema tables:

| Table | Role |
|-------|------|
| `dim_development` | Development / phase metadata |
| `dim_property` | Block, floor, unit |
| `dim_payment_term` | Standardized payment category |
| `fact_sales` | Transaction facts (price, dates, status) |

**Natural key:** `development|block|floor|unit|pasp_date` — supports idempotent UPSERT when SRPE amends or terminates sales.

**Transaction status:** `asp_signed` · `terminated` · `pasp_only`

SQL views for analytics (v2 dashboard):

- `vw_sales_detail` — denormalized transaction grain
- `vw_monthly_sales` — monthly aggregates
- `vw_block_summary` — per-block metrics

---

## Sample results (THE PAVILIA FARM III)

| Metric | Value |
|--------|-------|
| Transactions loaded | 1,145 |
| ASP signed | 654 |
| Terminated (撻訂) | 483 |
| PASP only | 8 |
| Payment: Cash plan | 763 |
| Payment: Stage payment | 375 |

---

## Design decisions

1. **One PDF per development** — matches SRPE publishing model; pipeline is development-scoped.
2. **UPSERT on `natural_key`** — handles price revisions and 撻訂 without duplicate rows.
3. **Bilingual payment mapping** — regex rules map 中文 / English terms to a single `standard_category`.
4. **SQLite ingestion log** — lightweight audit trail of extracted files (hash, page count, status).
5. **Secrets outside repo** — credentials in `.env`, never committed.

---

## Roadmap

- [x] v1 — Extract, Transform, Load
- [ ] v2 — Excel Power Query dashboard + screenshots
- [ ] Optional — text fallback parser for PDF pages pdfplumber cannot table-extract
- [ ] Optional — batch index over multiple HK developments

---

## Visualize (v2)

Planned: Excel Power Query dashboard on `vw_sales_detail` and related SQL views.  
Excel's PostgreSQL connector requires the **Npgsql** provider on Windows.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Author

Portfolio project — Data Analyst → Data Engineer path.  
Data source: [SRPE](https://www.srpe.gov.hk) (public government data).
