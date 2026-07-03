-- SRPE ETL star schema for PostgreSQL

CREATE TABLE IF NOT EXISTS dim_development (
  development_key SERIAL PRIMARY KEY,
  development_name_en TEXT NOT NULL UNIQUE,
  development_name_tc TEXT,
  phase_label TEXT,
  location_en TEXT,
  location_tc TEXT
);

CREATE TABLE IF NOT EXISTS dim_property (
  property_key SERIAL PRIMARY KEY,
  development_key INTEGER NOT NULL REFERENCES dim_development (development_key),
  block_name TEXT NOT NULL,
  floor TEXT NOT NULL,
  unit TEXT NOT NULL,
  property_natural_key TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dim_payment_term (
  payment_term_key SERIAL PRIMARY KEY,
  standard_category TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS fact_sales (
  sale_key BIGSERIAL PRIMARY KEY,
  natural_key TEXT NOT NULL UNIQUE,
  development_key INTEGER NOT NULL REFERENCES dim_development (development_key),
  property_key INTEGER NOT NULL REFERENCES dim_property (property_key),
  payment_term_key INTEGER NOT NULL REFERENCES dim_payment_term (payment_term_key),
  pasp_date DATE NOT NULL,
  asp_date DATE,
  termination_date DATE,
  price_hkd BIGINT NOT NULL,
  revised_price_hkd BIGINT,
  transaction_status TEXT NOT NULL,
  payment_primary_text TEXT,
  payment_terms_raw TEXT,
  related_party_raw TEXT,
  source_pdf TEXT,
  source_page INTEGER,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fact_sales_development_key
  ON fact_sales (development_key);

CREATE INDEX IF NOT EXISTS idx_fact_sales_payment_term_key
  ON fact_sales (payment_term_key);

CREATE INDEX IF NOT EXISTS idx_fact_sales_pasp_date
  ON fact_sales (pasp_date);

CREATE INDEX IF NOT EXISTS idx_fact_sales_transaction_status
  ON fact_sales (transaction_status);
