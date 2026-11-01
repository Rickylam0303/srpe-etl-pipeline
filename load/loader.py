"""Load transformed CSV rows into PostgreSQL using UPSERT."""

from __future__ import annotations

from pathlib import Path
import hashlib
import json

import pandas as pd
import psycopg

from load.db import connect
from transform.cleaners import normalize_identifier, build_natural_key, derive_transaction_status
from datetime import date


def _text(value) -> str | None:
  if value is None or (isinstance(value, float) and pd.isna(value)):
    return None
  text = str(value).strip()
  return text or None


def _int(value) -> int | None:
  if value is None or (isinstance(value, float) and pd.isna(value)):
    return None
  return int(value)


def _property_natural_key(development_name: str, block_name: str, floor, unit) -> str:
  return "|".join(
    [
      development_name.strip(),
      str(block_name).strip(),
      normalize_identifier(floor) or '',
      normalize_identifier(unit) or '',
    ]
  )


def upsert_development(cur: psycopg.Cursor, row: pd.Series) -> int:
  cur.execute(
    """
    INSERT INTO dim_development (
      development_name_en, development_name_tc, phase_label, location_en, location_tc
    ) VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (development_name_en) DO UPDATE SET
      development_name_tc = EXCLUDED.development_name_tc,
      phase_label = EXCLUDED.phase_label,
      location_en = EXCLUDED.location_en,
      location_tc = EXCLUDED.location_tc
    RETURNING development_key
    """,
    (
      row["development_name_en"],
      _text(row.get("development_name_tc")),
      _text(row.get("phase_label")),
      _text(row.get("location_en")),
      _text(row.get("location_tc")),
    ),
  )
  return int(cur.fetchone()[0])


def upsert_property(
  cur: psycopg.Cursor,
  *,
  development_key: int,
  block_name: str,
  floor,
  unit,
  property_natural_key: str,
) -> int:
  cur.execute(
    """
    INSERT INTO dim_property (
      development_key, block_name, floor, unit, property_natural_key
    ) VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (property_natural_key) DO UPDATE SET
      development_key = EXCLUDED.development_key,
      block_name = EXCLUDED.block_name,
      floor = EXCLUDED.floor,
      unit = EXCLUDED.unit
    RETURNING property_key
    """,
    (development_key, block_name, str(floor), str(unit), property_natural_key),
  )
  return int(cur.fetchone()[0])


def upsert_payment_term(cur: psycopg.Cursor, standard_category: str) -> int:
  cur.execute(
    """
    INSERT INTO dim_payment_term (standard_category)
    VALUES (%s)
    ON CONFLICT (standard_category) DO UPDATE SET
      standard_category = EXCLUDED.standard_category
    RETURNING payment_term_key
    """,
    (standard_category,),
  )
  return int(cur.fetchone()[0])


def upsert_fact_sale(
  cur: psycopg.Cursor,
  row: pd.Series,
  *,
  development_key: int,
  property_key: int,
  payment_term_key: int,
) -> str:
  cur.execute(
    """
    INSERT INTO fact_sales (
      natural_key, development_key, property_key, payment_term_key,
      pasp_date, asp_date, termination_date,
      price_hkd, revised_price_hkd, transaction_status,
      payment_primary_text, payment_terms_raw, related_party_raw,
      source_pdf, source_page
    ) VALUES (
      %s, %s, %s, %s,
      %s, %s, %s,
      %s, %s, %s,
      %s, %s, %s,
      %s, %s
    )
    ON CONFLICT (natural_key) DO UPDATE SET
      development_key = EXCLUDED.development_key,
      property_key = EXCLUDED.property_key,
      payment_term_key = EXCLUDED.payment_term_key,
      pasp_date = EXCLUDED.pasp_date,
      asp_date = EXCLUDED.asp_date,
      termination_date = EXCLUDED.termination_date,
      price_hkd = EXCLUDED.price_hkd,
      revised_price_hkd = EXCLUDED.revised_price_hkd,
      transaction_status = EXCLUDED.transaction_status,
      payment_primary_text = EXCLUDED.payment_primary_text,
      payment_terms_raw = EXCLUDED.payment_terms_raw,
      related_party_raw = EXCLUDED.related_party_raw,
      source_pdf = EXCLUDED.source_pdf,
      source_page = EXCLUDED.source_page,
      last_updated_at = NOW()
    RETURNING (xmax = 0) AS inserted
    """,
    (
      row["natural_key"],
      development_key,
      property_key,
      payment_term_key,
      row["pasp_date"],
      row["asp_date"] if pd.notna(row["asp_date"]) else None,
      row["termination_date"] if pd.notna(row["termination_date"]) else None,
      _int(row["price_hkd"]),
      _int(row["revised_price_hkd"]),
      row["transaction_status"],
      _text(row.get("payment_primary_text")),
      _text(row.get("payment_terms_raw")),
      _text(row.get("related_party_raw")),
      _text(row.get("source_pdf")),
      _int(row.get("source_page")),
    ),
  )
  inserted = bool(cur.fetchone()[0])
  return "inserted" if inserted else "updated"


def load_development_metadata(
  cur: psycopg.Cursor,
  staging_dir: Path,
  development_name_en: str,
) -> int | None:
  matches = list(staging_dir.glob("*_development.csv"))
  for path in matches:
    dev_df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    if dev_df.empty:
      continue
    row = dev_df.iloc[0]
    if row["development_name_en"] == development_name_en:
      return upsert_development(cur, row)
  return None


def load_transformed_csv(
  conn: psycopg.Connection,
  transformed_csv: Path,
  staging_dir: Path,
) -> dict[str, int]:
  report_path = transformed_csv.with_suffix('.quality.json')
  if report_path.exists():
    report = json.loads(report_path.read_text(encoding='utf-8'))
    if report.get('status') != 'passed' or report.get('output_sha256') != hashlib.sha256(transformed_csv.read_bytes()).hexdigest():
      raise ValueError(f'Failed or stale transform quality report: {report_path}')
    source_csv = Path(report['source_csv']) if report.get('source_csv') else None
    if source_csv and (not source_csv.exists() or hashlib.sha256(source_csv.read_bytes()).hexdigest() != report.get('source_sha256')):
      raise ValueError(f'Staging changed after transform: {source_csv}')
  df = pd.read_csv(transformed_csv, encoding="utf-8-sig", dtype=str, keep_default_na=False)
  if df.empty:
    return {"rows": 0, "inserted": 0, "updated": 0}

  for filename in df['source_pdf'].unique():
    extraction_path = staging_dir / f'{Path(filename).stem}_extraction_quality.json'
    if extraction_path.exists() and json.loads(extraction_path.read_text(encoding='utf-8')).get('status') != 'passed':
      raise ValueError(f'Unresolved extraction quality report: {extraction_path}')

  if df['development_name_en'].nunique() != 1 or df['natural_key'].duplicated().any():
    raise ValueError('Load requires one development and unique transaction keys per file')
  for _, row in df.iterrows():
    if any(not str(row[c]).strip() for c in ['block_name', 'floor', 'unit', 'development_name_en']):
      raise ValueError('Missing property identity')
    dates = {c: date.fromisoformat(row[c]) if row[c] else None
             for c in ['pasp_date', 'asp_date', 'termination_date']}
    expected_key = build_natural_key(development_name=row['development_name_en'],
      block_name=row['block_name'], floor=row['floor'], unit=row['unit'], pasp_date=dates['pasp_date'])
    status = derive_transaction_status(termination_date=dates['termination_date'],
      asp_date=dates['asp_date'], pasp_date=dates['pasp_date'])
    if not dates['pasp_date'] or expected_key != row['natural_key'] or status != row['transaction_status']:
      raise ValueError('Inconsistent transaction identity or status')
    if int(row['price_hkd']) <= 0 or (row['revised_price_hkd'] and int(row['revised_price_hkd']) <= 0):
      raise ValueError('Contract prices must be positive integers')
  df['revised_price_hkd'] = df['revised_price_hkd'].replace('', None)
  df['asp_date'] = df['asp_date'].replace('', None)
  df['termination_date'] = df['termination_date'].replace('', None)

  development_name = df.iloc[0]["development_name_en"]
  inserted = 0
  updated = 0

  with conn.cursor() as cur:
    development_key = load_development_metadata(cur, staging_dir, development_name)
    if development_key is None:
      development_key = upsert_development(
        cur,
        pd.Series(
          {
            "development_name_en": development_name,
            "development_name_tc": None,
            "phase_label": None,
            "location_en": None,
            "location_tc": None,
          }
        ),
      )

    for _, row in df.iterrows():
      property_key = upsert_property(
        cur,
        development_key=development_key,
        block_name=row["block_name"],
        floor=row["floor"],
        unit=row["unit"],
        property_natural_key=_property_natural_key(
          development_name,
          row["block_name"],
          row["floor"],
          row["unit"],
        ),
      )
      payment_term_key = upsert_payment_term(cur, row["payment_category"])
      action = upsert_fact_sale(
        cur,
        row,
        development_key=development_key,
        property_key=property_key,
        payment_term_key=payment_term_key,
      )
      if action == "inserted":
        inserted += 1
      else:
        updated += 1

  conn.commit()
  return {"rows": len(df), "inserted": inserted, "updated": updated}


def load_all_transformed_files(
  settings: dict,
  transformed_dir: Path,
  staging_dir: Path,
) -> list[dict[str, int | str]]:
  results: list[dict[str, int | str]] = []
  with connect(settings) as conn:
    for transformed_csv in sorted(transformed_dir.glob("*_transactions_clean.csv")):
      summary = load_transformed_csv(conn, transformed_csv, staging_dir)
      summary["file"] = transformed_csv.name
      results.append(summary)
  return results
