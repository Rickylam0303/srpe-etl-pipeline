-- Denormalized views for Excel Power Query dashboards

CREATE OR REPLACE VIEW vw_sales_detail AS
SELECT
  f.sale_key,
  f.natural_key,
  d.development_name_en,
  d.development_name_tc,
  d.phase_label,
  d.location_en,
  p.block_name,
  p.floor,
  p.unit,
  pt.standard_category AS payment_category,
  f.pasp_date,
  f.asp_date,
  f.termination_date,
  f.price_hkd,
  f.revised_price_hkd,
  COALESCE(f.revised_price_hkd, f.price_hkd) AS final_price_hkd,
  f.transaction_status,
  f.payment_primary_text,
  f.source_pdf,
  f.source_page,
  DATE_TRUNC('month', f.pasp_date)::date AS pasp_month,
  EXTRACT(YEAR FROM f.pasp_date)::int AS pasp_year,
  CASE WHEN f.transaction_status = 'terminated' THEN 1 ELSE 0 END AS is_terminated,
  CASE WHEN f.transaction_status = 'asp_signed' THEN 1 ELSE 0 END AS is_asp_signed,
  CASE WHEN f.transaction_status = 'pasp_only' THEN 1 ELSE 0 END AS is_pasp_only
FROM fact_sales f
JOIN dim_development d ON f.development_key = d.development_key
JOIN dim_property p ON f.property_key = p.property_key
JOIN dim_payment_term pt ON f.payment_term_key = pt.payment_term_key;

CREATE OR REPLACE VIEW vw_monthly_sales AS
SELECT
  development_name_en,
  pasp_month,
  COUNT(*) AS transaction_count,
  COUNT(*) FILTER (WHERE transaction_status = 'asp_signed') AS asp_signed_count,
  COUNT(*) FILTER (WHERE transaction_status = 'terminated') AS terminated_count,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE transaction_status = 'terminated') / NULLIF(COUNT(*), 0),
    1
  ) AS termination_rate_pct,
  ROUND(AVG(final_price_hkd)) AS avg_price_hkd,
  MIN(final_price_hkd) AS min_price_hkd,
  MAX(final_price_hkd) AS max_price_hkd
FROM vw_sales_detail
GROUP BY development_name_en, pasp_month
ORDER BY development_name_en, pasp_month;

CREATE OR REPLACE VIEW vw_block_summary AS
SELECT
  development_name_en,
  block_name,
  COUNT(*) AS transaction_count,
  COUNT(*) FILTER (WHERE transaction_status = 'asp_signed') AS asp_signed_count,
  COUNT(*) FILTER (WHERE transaction_status = 'terminated') AS terminated_count,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE transaction_status = 'terminated') / NULLIF(COUNT(*), 0),
    1
  ) AS termination_rate_pct,
  ROUND(AVG(final_price_hkd)) AS avg_price_hkd
FROM vw_sales_detail
GROUP BY development_name_en, block_name
ORDER BY development_name_en, block_name;
