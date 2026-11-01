# Validation record

Validation performed on 2026-10-31 and 2026-11-01 (Asia/Shanghai).
Scope: the reviewed THE PAVILIA FARM III historical register and the bundled
regression fixture. This records executed checks, not a certification of every
source field or every SRPE register layout.

## Environment and reproducibility

- Windows; Python 3.13.13; PostgreSQL 18.4 on localhost.
- A separate `.venv-repro` was created, installed from
  [requirements-lock.txt](../requirements-lock.txt), and passed `pip check`.
- The three CLIs were exercised in that environment. The fixture path using
  [config/demo.yaml](../config/demo.yaml) produced 15 raw and 15 clean records.
  The full local PDF produced 1,183 raw and 1,183 clean records.
- The source identity, submission timestamp, SHA-256 and 38 known omitted
  pages are recorded in [source_snapshot.json](source_snapshot.json).
  The submission timestamp was checked against the locally retained SRPE API
  response for that filename. The historical PDF itself is not bundled.

Full PDF SHA-256:

```text
06bb7fe8fda1f6eb66ecda650e63a3cdaf2a619dd9d4141daf891fdfd903216a
```

## Executed checks

| Area | Verified result |
|---|---|
| PDF reconciliation | 706 pages processed; all candidate transaction counts reconciled; 38 previously omitted records recovered; no duplicate natural keys |
| Source correction | Struck-out ASP date on original page 285 excluded; effective date 2021-06-21 retained; the page was visually inspected |
| Failed extraction | A suspected transaction page with no resolved rows writes structured failure details and is not published as successful staging |
| Search batch failure | A failed development causes a nonzero batch failure after logging; successful developments can remain for retry |
| Version handling | Same remote version and matching local hash can skip download; changed version or hash requests download; source URL/time survive parsing (offline tests) |
| Cleaning | Invalid identifiers, dates, prices and duplicate keys rejected; failed transform preserves the previous clean CSV; errors and warnings reported separately |
| Amendments | Latest dated price/payment selection checked independently against source text; undated, invalid or ambiguous revisions rejected |
| Payment audit | 121 initial-to-latest classification changes checked, including all 84 previously identified differences; raw text, source pages and keys retained in the audit |
| Database | Full load and reload preserve row counts; same-key amendment updates the existing sale key; invalid quality report blocks loading |
| SQL | All six sample queries execute; 61 consecutive months include zero-transaction months; empty-cohort rate remains NULL; price aggregates use ASP-signed records |
| Display database | After isolated tests passed, existing display database updated without deletion; all 1,183 keys and checked dates, prices, status and payment values match clean CSV; monthly counts match summary |
| Excel | Actual PostgreSQL Refresh All exercised after the user enabled workbook content; refreshed detail table has 1,183 records; native queries and pivots retained |
| Saved Excel | Saved OOXML caches checked for KPI values, 61 monthly counts and table range A1:Y1184; chart labels distinguish ASP-signed prices and all-contract payment counts |
| Reference image | `python -m visualize.report --png` passed source/report/hash checks; regenerated SVG and PNG visually inspected; this image is not an Excel screenshot |

The payment audit is an automated row-by-row source-label comparison, with
selected examples visually inspected. It is not a manual review of all 121
amendments. See [payment_revision_audit.csv](payment_revision_audit.csv).

Final test invocation in the clean environment:

```powershell
$env:SRPE_RUN_DB_TESTS = '1'
$env:SRPE_TEST_FULL_CSV = 'data/transformed/THE_PAVILIA_FARM_III_transactions_clean.csv'
.\.venv-repro\Scripts\python -B -m unittest discover -s tests -v
```

Result: **8 tests passed** (7 offline regression tests and 1 PostgreSQL
integration test). The integration test creates a UUID-named `srpe_test_*`
database and removes only that isolated test database afterward. The existing
display database was not deleted.

## Reconciled snapshot

| Metric | Result |
|---|---:|
| Contract records | 1,183 |
| Unique properties | 857 |
| ASP signed | 682 |
| Terminated | 494 |
| PASP only, explicitly not proceeded further | 7 |
| Terminated / all contract records | 41.76% |
| Mean latest contract price, ASP signed | HK$15,612,120.41 |
| Latest cash / stage / unmapped payment categories | 874 / 302 / 7 |
| PASP period | 2021-06-05 to 2026-06-21 |
| Continuous calendar months | 61 |
| Quality errors / warnings | 0 / 15 |

The 15 warnings comprise seven not-proceeded statements, seven unmapped payment
plans and one ASP date preceding its PASP date on original page 247. The last
contradiction is present in the source; original dates are preserved rather
than guessed. Counts are contracts, not distinct units. Signed ASP does not
establish completion. Machine-readable values are in
[snapshot_summary.json](snapshot_summary.json).

## Remaining limitations

- The current live SRPE download/search service was not revalidated over the
  network in this change. Remote version behavior was exercised offline.
  Availability of this exact historical PDF from the live service is not
  guaranteed; hash-check any supplied copy. The bundled 15-record fixture
  provides a reproducible path without that historical download.
- Other PDF layouts, Python/PostgreSQL versions, operating systems and Excel
  connector installations were not verified. Parser reconciliation detects
  the known candidate pattern; it does not prove no entirely different source
  layout could be missed. OCR is not implemented.
- This is not a manual field-by-field audit of all 1,183 records. Warnings
  remain visible and unsupported market-cycle, premium and mortgage-risk
  claims have been removed.
- Natural-key amendments update existing rows. A correction to an identity
  field changes the key; automatic identity merging and source-deletion
  reconciliation are outside scope.
- The local Excel monthly chart uses `public vw_sales_detail!AE1:AF62`, with
  DATE/TEXT/COUNTIFS formulas covering June 2021 through June 2026. New source
  periods require extending these formulas and the chart range, or loading
  `vw_monthly_sales`, which generates the calendar dynamically. The old
  grouped pivot at AA1 is retained as a supporting pivot and does not drive
  the monthly chart. The workbook is ignored by Git; published reproduction
  uses the documented SQL/Excel setup and reference image.
