# Reporting and Excel setup

`dashboard.svg` and `dashboard.png` are reference charts rendered from the
checked clean CSV by `python -m visualize.report --png`. The builder first
verifies the historical PDF hash, page reconciliation, clean-file hash,
snapshot counts and individual amendment classifications. The PNG is not an
Excel screenshot. Rebuilding it requires Playwright Chromium:

```powershell
.\.venv\Scripts\python -m playwright install chromium
.\.venv\Scripts\python -m visualize.report --png
```

The local `SRPE_Dashboard.xlsx` is ignored by Git. It retains the existing
Power Query connection and native pivots; do not publish a workbook containing
saved database credentials. The steps below also let another reader recreate
the Excel view without receiving that local file.

## Connect and refresh

1. Run Extract, Transform and Load in the repository README, then create the SQL
   views with `python run_load.py --init-views`.
2. In Excel, choose **Data > Get Data > From PostgreSQL database**. Use the host,
   database and account configured for your installation. The reviewed full
   snapshot uses `localhost` / `srpe_etl`; the fixture example uses
   `srpe_etl_demo`. If Excel requests a provider, follow the connector's own
   installation instructions for your Excel version and architecture.
3. Load `public.vw_sales_detail` as a worksheet table. The starter query is
   [power_query_sales_detail.m](power_query_sales_detail.m). Expected full
   snapshot: **1,183 rows**. Fixture demo: **15 rows**.
4. Choose **Refresh All**, wait for the source query to finish, then refresh
   pivots if they have retained the previous cache. Compare counts with the
   checked snapshot summary; a successful connection alone is insufficient.
5. If Excel disables external connections, the user must decide whether to
   enable the trusted workbook's content. Do not change global Trust Center
   settings just to reproduce this example.

## Metric definitions

Use your actual table name in formulas. The existing local workbook uses
`public_vw_sales_detail`.

| Metric | Formula / source |
|---|---|
| Contract count | `=COUNTA(public_vw_sales_detail[natural_key])` |
| ASP signed | `=COUNTIFS(public_vw_sales_detail[transaction_status],"asp_signed")` |
| Terminated | `=COUNTIFS(public_vw_sales_detail[transaction_status],"terminated")` |
| Termination rate | Terminated / contract count |
| ASP-signed mean price | `=AVERAGEIFS(public_vw_sales_detail[final_price_hkd],public_vw_sales_detail[transaction_status],"asp_signed")` |

`final_price_hkd` is the latest dated revised price, otherwise the original
price. ASP signed is not proof of completion. The seven PASP-only records in
the reviewed snapshot explicitly did not proceed further; they are not
presented as pending transactions.

## Charts

- **Monthly contracts:** Prefer loading `vw_monthly_sales`, which contains every
  month between a development's first and last PASP month, including zero counts.
  Format real dates as `yyyy-mm`, sort chronologically and use a line chart.
  Never group only by month number across years. The reviewed local workbook
  instead uses `public vw_sales_detail!AE1:AF62`: DATE/TEXT formulas generate
  June 2021 through June 2026 and COUNTIFS counts the detail table for each
  month, including zeros. Extend those formulas and the chart range for later
  snapshots, or connect the chart to `vw_monthly_sales` for a dynamic calendar.
  The supporting grouped pivot at AA1 does not drive this chart.
- **Block prices:** Use `vw_block_summary.avg_price_hkd`, or filter a detail
  pivot to `transaction_status = asp_signed` before averaging `final_price_hkd`.
  Label the chart **ASP-signed mean contract price (HK$)**. This is not a price
  per square foot or an adjusted tower premium.
- **Payment mix:** Count all contract records by `payment_category`, which is
  now the latest effective dated plan. Keep `Unmapped` visible. Label the chart
  **Latest payment plan — all contract records**.

Show the development, source version and PASP date range alongside the charts.
The reviewed snapshot spans **2021-06-05 to 2026-06-21**, with source submission
on **2026-06-26**. Termination rates in monthly views are PASP-cohort status
ratios, not monthly termination-event rates.

See [validation evidence](../docs/VALIDATION.md) for what was actually exercised
on the installed Excel and PostgreSQL environment.
