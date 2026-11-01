-- Sample analytics queries for SRPE ETL portfolio
-- Database: srpe_etl (PostgreSQL)
-- Run after: python run_load.py --init-views

-- 1) Overall transaction status mix
SELECT
  transaction_status,
  COUNT(*) AS transaction_count,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_of_total
FROM vw_sales_detail
GROUP BY transaction_status
ORDER BY transaction_count DESC;

-- 2) Monthly sales volume and termination rate
SELECT
  pasp_month,
  transaction_count,
  asp_signed_count,
  terminated_count,
  termination_rate_pct,
  avg_price_hkd
FROM vw_monthly_sales
ORDER BY pasp_month;

-- 3) Top blocks by ASP-signed average contract price (not an area-adjusted premium)
SELECT
  block_name,
  transaction_count,
  asp_signed_count,
  terminated_count,
  termination_rate_pct,
  avg_price_hkd
FROM vw_block_summary
ORDER BY avg_price_hkd DESC
LIMIT 10;

-- 4) Payment method mix
SELECT
  payment_category,
  COUNT(*) AS transaction_count,
  ROUND(AVG(final_price_hkd) FILTER (WHERE transaction_status = 'asp_signed')) AS avg_price_hkd
FROM vw_sales_detail
GROUP BY payment_category
ORDER BY transaction_count DESC;

-- 5) Recent amendments / terminations (data quality audit)
SELECT
  development_name_en,
  block_name,
  floor,
  unit,
  pasp_date,
  transaction_status,
  price_hkd,
  revised_price_hkd,
  final_price_hkd,
  termination_date
FROM vw_sales_detail
WHERE transaction_status = 'terminated'
ORDER BY termination_date DESC NULLS LAST, pasp_date DESC
LIMIT 20;

-- 6) Highest-volume PASP months, separately per development
SELECT
  development_name_en,
  pasp_month,
  transaction_count,
  avg_price_hkd
FROM vw_monthly_sales
ORDER BY transaction_count DESC, development_name_en, pasp_month
LIMIT 3;
