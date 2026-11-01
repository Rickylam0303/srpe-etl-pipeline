"""Transform staging data with explicit rejection and source-warning reports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from transform.cleaners import (
  build_natural_key, derive_transaction_status, normalize_block_name,
  normalize_identifier, parse_hk_date, parse_price_hkd, parse_revised_price_hkd,
)
from transform.payment_mapper import extract_primary_payment_text, map_payment_category

CLEAN_COLUMNS = [
  'natural_key', 'development_name_en', 'pasp_date', 'asp_date', 'termination_date',
  'block_name', 'floor', 'unit', 'parking', 'price_hkd', 'revised_price_hkd',
  'payment_category', 'payment_primary_text', 'payment_terms_raw',
  'transaction_status', 'related_party_raw', 'source_pdf', 'source_page',
]


class TransformQualityError(ValueError):
  """Rejected source rows must be resolved before publishing a clean batch."""


def transform_transactions_df(df: pd.DataFrame) -> pd.DataFrame:
  records, issues, seen = [], [], set()
  for index, row in enumerate(df.to_dict('records'), start=2):
    errors, warnings = [], []
    identity = {c: normalize_identifier(row.get(c))
                for c in ['development_name_en', 'floor', 'unit']}
    identity['block_name'] = normalize_block_name(row.get('block_name'))
    for field, value in identity.items():
      if not value or value == 'UNKNOWN' or '|' in value:
        errors.append(f'invalid_{field}')
    dates = {}
    for field in ['pasp_date', 'asp_date', 'termination_date']:
      raw = normalize_identifier(row.get(field))
      dates[field] = parse_hk_date(raw)
      if field == 'asp_date' and raw and 'the pasp has not proceeded further' in raw.lower():
        warnings.append('pasp_not_proceeded')
      elif raw and dates[field] is None:
        errors.append(f'invalid_{field}')
      elif field == 'pasp_date' and not raw:
        errors.append('missing_pasp_date')
    price = parse_price_hkd(row.get('price_raw'))
    if price is None:
      errors.append('invalid_price_hkd')
    revised, primary, category = None, '', 'Unmapped'
    try:
      revised = parse_revised_price_hkd(row.get('price_revision_raw'))
    except ValueError as exc:
      errors.append(str(exc))
    try:
      primary = extract_primary_payment_text(row.get('payment_terms_raw'))
      category = map_payment_category(row.get('payment_terms_raw'))
    except ValueError as exc:
      errors.append(str(exc))
    if category == 'Unmapped':
      warnings.append('unmapped_payment')
    pasp = dates['pasp_date']
    for field in ['asp_date', 'termination_date']:
      if pasp and dates[field] and dates[field] < pasp:
        warnings.append(f'{field}_before_pasp_date')
    if dates['asp_date'] and dates['termination_date'] and dates['termination_date'] < dates['asp_date']:
      warnings.append('termination_before_asp_date')
    natural_key = None
    if not errors:
      natural_key = build_natural_key(
        development_name=identity['development_name_en'], block_name=identity['block_name'],
        floor=identity['floor'], unit=identity['unit'], pasp_date=pasp)
      if natural_key in seen:
        errors.append('duplicate_natural_key')
      seen.add(natural_key)
    for severity, reasons in [('error', errors), ('warning', warnings)]:
      for reason in reasons:
        issues.append({
          'csv_row': index, 'source_pdf': normalize_identifier(row.get('source_pdf')),
          'source_page': normalize_identifier(row.get('source_page')), 'natural_key': natural_key,
          'severity': severity, 'reason': reason, 'raw_row': row,
        })
    if errors:
      continue
    records.append({
      'natural_key': natural_key, **identity, **dates, 'price_hkd': price,
      'revised_price_hkd': revised, 'payment_primary_text': primary,
      'payment_category': category, 'transaction_status': derive_transaction_status(
        termination_date=dates['termination_date'], asp_date=dates['asp_date'], pasp_date=pasp),
      **{c: row.get(c) for c in ['parking', 'payment_terms_raw', 'related_party_raw',
                                'source_pdf', 'source_page']},
    })
  transformed = pd.DataFrame(records, columns=CLEAN_COLUMNS)
  for field in ['price_hkd', 'revised_price_hkd']:
    transformed[field] = transformed[field].astype('Int64')
  transformed.attrs['quality_issues'] = issues
  return transformed


def transform_staging_csv(staging_csv: Path, output_csv: Path) -> dict:
  df = pd.read_csv(staging_csv, encoding='utf-8-sig', dtype=str, keep_default_na=False)
  transformed = transform_transactions_df(df)
  issues = transformed.attrs['quality_issues']
  errors = [issue for issue in issues if issue['severity'] == 'error']
  report_path = output_csv.with_suffix('.quality.json')
  summary = {
    'input_rows': len(df), 'output_rows': len(transformed),
    'dropped_rows': len(df) - len(transformed),
    'unmapped_payment_rows': int((transformed['payment_category'] == 'Unmapped').sum()),
    'warning_count': sum(issue['severity'] == 'warning' for issue in issues),
    'output_csv': str(output_csv), 'quality_report': str(report_path),
  }
  report = {**summary, 'status': 'failed' if errors or df.empty else 'passed',
            'source_csv': str(staging_csv.resolve()),
            'source_sha256': hashlib.sha256(staging_csv.read_bytes()).hexdigest(),
            'issues': issues}
  if df.empty:
    report['issues'].append({'severity': 'error', 'reason': 'empty_batch'})
  output_csv.parent.mkdir(parents=True, exist_ok=True)
  if report['status'] == 'passed':
    temporary = output_csv.with_suffix('.csv.tmp')
    transformed.to_csv(temporary, index=False, encoding='utf-8-sig')
    temporary.replace(output_csv)
    report['output_sha256'] = hashlib.sha256(output_csv.read_bytes()).hexdigest()
  report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
  if report['status'] == 'failed':
    raise TransformQualityError(f'Batch rejected; see {report_path}')
  return summary


def transform_all_staging_files(staging_dir: Path, transformed_dir: Path) -> list[dict]:
  results = []
  for staging_csv in sorted(staging_dir.glob('*_transactions_raw.csv')):
    stem = staging_csv.name.removesuffix('_transactions_raw.csv')
    summary = transform_staging_csv(staging_csv, transformed_dir / f'{stem}_transactions_clean.csv')
    summary['development'] = stem
    results.append(summary)
  return results
