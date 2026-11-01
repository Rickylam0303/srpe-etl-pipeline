# Resume and application copy

Choose the version closest to the vacancy; use three bullets for one project.
These describe verified project results, without claiming production scale,
commercial impact or employment experience.

## Junior Data Analyst

**SRPE Residential Sales Analysis | Python, SQL, PostgreSQL, Excel**

- Transformed a 706-page bilingual residential transaction register into
  1,183 traceable contract records, recovering 38 omitted records through
  page-level extraction checks.
- Built six SQL analyses and an Excel dashboard with 61 consecutive reporting
  months; separated all-contract counts from ASP-signed price averages and
  reconciled results across CSV, PostgreSQL and Excel.
- Audited 121 payment-category amendments against source labels, including
  84 previously identified discrepancies; documented 15 remaining warnings
  and removed conclusions unsupported by the dataset.

## Junior Data Engineer

**SRPE PDF-to-PostgreSQL ETL | Python, pandas, PostgreSQL, SQL**

- Implemented PDF extraction, validation and PostgreSQL loading for 1,183
  contract records, with page reconciliation, source hashes and structured
  quality reports that block unresolved batches.
- Used contract natural keys and UPSERT to support repeat loads and dated
  price/payment revisions while retaining raw terms and source-page lineage;
  verified reloads and same-key updates in an isolated database.
- Added eight regression/integration tests and a bundled 15-record fixture;
  verified clean-environment reproduction with locked dependencies and
  execution of all six SQL examples.

## Short project description

Built a Python and PostgreSQL pipeline that turns bilingual Hong Kong property
transaction PDFs into validated contract records and SQL/Excel reports.
Recovered 38 omitted records, implemented latest-dated amendment handling,
and verified the 1,183-record snapshot through regression tests and reporting
reconciliation. Includes an offline fixture, reproducible setup and explicit
data limitations.

## Application links

Use the repository URL as the project link and link directly to
[the project brief](PORTFOLIO.md) for a quick overview. Keep
[the validation evidence](VALIDATION.md) available for technical review.
Do not attach the local workbook with saved database credentials. The
[reference dashboard](../visualize/dashboard.png) is suitable for a portfolio
preview with its source period and metric definitions retained.
