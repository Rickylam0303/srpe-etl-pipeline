"""Pandas transform pipeline from staging CSV to load-ready CSV."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from transform.cleaners import (
  build_natural_key,
  derive_transaction_status,
  normalize_block_name,
  parse_hk_date,
  parse_price_hkd,
  parse_revised_price_hkd,
)
from transform.payment_mapper import extract_primary_payment_text, map_payment_category


def transform_transactions_df(df: pd.DataFrame) -> pd.DataFrame:
  if df.empty:
    return pd.DataFrame()

  working = df.copy()

  working["pasp_date_parsed"] = working["pasp_date"].map(parse_hk_date)
  working["asp_date_parsed"] = working["asp_date"].map(parse_hk_date)
  working["termination_date_parsed"] = working["termination_date"].map(parse_hk_date)
  working["block_name_clean"] = working["block_name"].map(normalize_block_name)
  working["price_hkd"] = working["price_raw"].map(parse_price_hkd)
  working["revised_price_hkd"] = working["price_revision_raw"].map(parse_revised_price_hkd)
  working["payment_primary_text"] = working["payment_terms_raw"].map(extract_primary_payment_text)
  working["payment_category"] = working["payment_terms_raw"].map(map_payment_category)
  working["transaction_status"] = working.apply(
    lambda row: derive_transaction_status(
      termination_date=row["termination_date_parsed"],
      asp_date=row["asp_date_parsed"],
      pasp_date=row["pasp_date_parsed"],
    ),
    axis=1,
  )
  working["natural_key"] = working.apply(
    lambda row: build_natural_key(
      development_name=row["development_name_en"],
      block_name=row["block_name_clean"],
      floor=row.get("floor"),
      unit=row.get("unit"),
      pasp_date=row["pasp_date_parsed"],
    ),
    axis=1,
  )

  transformed = pd.DataFrame(
    {
      "natural_key": working["natural_key"],
      "development_name_en": working["development_name_en"],
      "pasp_date": working["pasp_date_parsed"],
      "asp_date": working["asp_date_parsed"],
      "termination_date": working["termination_date_parsed"],
      "block_name": working["block_name_clean"],
      "floor": working["floor"],
      "unit": working["unit"],
      "parking": working["parking"],
      "price_hkd": working["price_hkd"],
      "revised_price_hkd": working["revised_price_hkd"],
      "payment_category": working["payment_category"],
      "payment_primary_text": working["payment_primary_text"],
      "payment_terms_raw": working["payment_terms_raw"],
      "transaction_status": working["transaction_status"],
      "related_party_raw": working["related_party_raw"],
      "source_pdf": working["source_pdf"],
      "source_page": working["source_page"],
    }
  )

  valid_mask = transformed["pasp_date"].notna() & transformed["price_hkd"].notna()
  transformed = transformed.loc[valid_mask].reset_index(drop=True)
  transformed["price_hkd"] = transformed["price_hkd"].astype("Int64")
  transformed["revised_price_hkd"] = transformed["revised_price_hkd"].astype("Int64")
  return transformed


def transform_staging_csv(staging_csv: Path, output_csv: Path) -> dict[str, int | str]:
  df = pd.read_csv(staging_csv, encoding="utf-8-sig")
  transformed = transform_transactions_df(df)

  output_csv.parent.mkdir(parents=True, exist_ok=True)
  transformed.to_csv(output_csv, index=False, encoding="utf-8-sig")

  unmapped_count = int((transformed["payment_category"] == "Unmapped").sum()) if not transformed.empty else 0
  dropped_rows = len(df) - len(transformed)
  return {
    "input_rows": len(df),
    "output_rows": len(transformed),
    "dropped_rows": dropped_rows,
    "unmapped_payment_rows": unmapped_count,
    "output_csv": str(output_csv),
  }


def transform_all_staging_files(staging_dir: Path, transformed_dir: Path) -> list[dict[str, int | str]]:
  results: list[dict[str, int | str]] = []
  for staging_csv in sorted(staging_dir.glob("*_transactions_raw.csv")):
    stem = staging_csv.name.replace("_transactions_raw.csv", "")
    output_csv = transformed_dir / f"{stem}_transactions_clean.csv"
    summary = transform_staging_csv(staging_csv, output_csv)
    summary["development"] = stem
    results.append(summary)
  return results
