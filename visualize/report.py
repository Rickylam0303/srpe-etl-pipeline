"""Reproduce the checked snapshot summary, amendment audit and reference chart.

Run from the repository root: python -m visualize.report [--png]
The PNG is a rendered report from clean CSV, not an Excel refresh screenshot.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
from html import escape
import json
from pathlib import Path
import re

import pandas as pd

from transform.payment_mapper import map_payment_category

ROOT = Path(__file__).resolve().parents[1]


def build_report() -> dict:
  manifest = json.loads((ROOT / 'docs/source_snapshot.json').read_text(encoding='utf-8'))
  pdf = ROOT / 'data/raw/pdfs' / manifest['file_name']
  if hashlib.sha256(pdf.read_bytes()).hexdigest() != manifest['sha256']:
    raise ValueError('PDF differs from the documented snapshot; do not reuse its expected KPIs')
  staging = ROOT / 'data/staging/THE_PAVILIA_FARM_III_transactions_raw.csv'
  clean = ROOT / 'data/transformed/THE_PAVILIA_FARM_III_transactions_clean.csv'
  extraction = json.loads((staging.parent / f'{pdf.stem}_extraction_quality.json').read_text(encoding='utf-8'))
  quality = json.loads(clean.with_suffix('.quality.json').read_text(encoding='utf-8'))
  if extraction['status'] != 'passed' or extraction['sha256'] != manifest['sha256']:
    raise ValueError('Extraction reconciliation has not passed for this PDF')
  if quality['status'] != 'passed' or quality['output_sha256'] != hashlib.sha256(clean.read_bytes()).hexdigest():
    raise ValueError('Clean CSV has a failed or stale quality report')
  if quality['source_sha256'] != hashlib.sha256(staging.read_bytes()).hexdigest():
    raise ValueError('Staging changed since the last transform')
  raw = pd.read_csv(staging, dtype=str, keep_default_na=False)
  df = pd.read_csv(clean, dtype={'floor': str, 'unit': str}, keep_default_na=False)
  if not (len(raw) == len(df) == extraction['transaction_count'] == manifest['expected_transactions']):
    raise ValueError('Snapshot row reconciliation failed')
  if df.natural_key.duplicated().any():
    raise ValueError('Duplicate transaction identities')
  recovered = sorted(p['source_page'] for p in extraction['pages'] if p['fallback'])
  if recovered != manifest['previously_missed_pages']:
    raise ValueError('Recovered pages differ from the reviewed source snapshot')
  audit = []
  marker_pattern = r'On\s+(\d{2}/\d{2}/\d{4}),?\s+the terms of payment adjusted to'
  for source, result in zip(raw.to_dict('records'), df.to_dict('records')):
    price_events = re.findall(r'On\s+(\d{2}/\d{2}/\d{4}),?\s+the price adjusted to\s*\$([\d,]+)', source['price_revision_raw'], re.I)
    if price_events:
      latest_price = max(price_events, key=lambda pair: datetime.strptime(pair[0], '%d/%m/%Y'))
      if int(result['revised_price_hkd']) != int(latest_price[1].replace(',', '')):
        raise ValueError(f"Price amendment disagreement on page {source['source_page']}")
    markers = list(re.finditer(marker_pattern, source['payment_terms_raw'], re.I))
    if not markers:
      continue
    initial_match = re.search(r'付款方法[:：]\s*(.+?)(?:terms of payment|$)', source['payment_terms_raw'], re.I)
    if not initial_match:
      raise ValueError('Initial amended payment method not identifiable')
    initial = map_payment_category(initial_match.group(1))
    latest = result['payment_category']
    selected = max(range(len(markers)), key=lambda i: datetime.strptime(markers[i].group(1), '%d/%m/%Y'))
    start = markers[selected].end()
    end = markers[selected + 1].start() if selected + 1 < len(markers) else len(source['payment_terms_raw'])
    segment = source['payment_terms_raw'][start:end]
    # Independent English-label check on each amended source segment.
    expected = ('Stage Payment' if re.search(r'stage\s*payment', segment, re.I)
                else 'Cash Payment Plan' if re.search(r'day[- ]?cash\s*payment', segment, re.I)
                else None)
    if expected and latest != expected:
      raise ValueError(f"Payment amendment disagreement on page {source['source_page']}")
    if initial != latest:
      audit.append({'natural_key': result['natural_key'], 'source_page': int(source['source_page']),
                    'initial_category': initial, 'latest_category': latest,
                    'latest_amendment_date': datetime.strptime(markers[selected].group(1), '%d/%m/%Y').date().isoformat(),
                    'in_previous_extract': int(source['source_page']) not in recovered})
  audit_frame = pd.DataFrame(audit)
  original_changes = int(audit_frame.in_previous_extract.sum())
  if original_changes != 84:
    raise ValueError('The 84 previously identified category changes did not reconcile')
  audit_frame.to_csv(ROOT / 'docs/payment_revision_audit.csv', index=False, encoding='utf-8-sig')
  dates = pd.to_datetime(df.pasp_date)
  months = pd.date_range(dates.min().replace(day=1), dates.max().replace(day=1), freq='MS')
  monthly = dates.dt.to_period('M').astype(str).value_counts().reindex(months.strftime('%Y-%m'), fill_value=0)
  df['final_price_hkd'] = pd.to_numeric(df.revised_price_hkd, errors='coerce').fillna(df.price_hkd)
  signed = df[df.transaction_status == 'asp_signed']
  status, payments = df.transaction_status.value_counts().to_dict(), df.payment_category.value_counts().to_dict()
  summary = {
    'source_sha256': manifest['sha256'], 'source_submission_time': manifest['submission_time'],
    'pasp_date_min': str(dates.min().date()), 'pasp_date_max': str(dates.max().date()),
    'transactions': len(df), 'unique_properties': int(df[['block_name','floor','unit']].drop_duplicates().shape[0]),
    'status_counts': status, 'termination_rate_pct': round(100 * status.get('terminated', 0) / len(df), 2),
    'asp_signed_avg_price_hkd': round(float(signed.final_price_hkd.mean()), 2),
    'latest_payment_counts': payments,
    'asp_signed_block_avg_price_hkd': {str(k): round(float(v), 2) for k,v in signed.groupby('block_name').final_price_hkd.mean().items()},
    'monthly_contract_counts': {str(k): int(v) for k,v in monthly.items()},
    'recovered_transactions': len(recovered), 'payment_category_changes': len(audit),
    'previously_identified_payment_changes_checked': original_changes,
    'quality_warnings': quality['warning_count'], 'quality_errors': 0,
    'warning_counts': pd.Series([i['reason'] for i in quality['issues']]).value_counts().to_dict(),
  }
  (ROOT / 'docs/snapshot_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
  render_svg(summary)
  return summary


def render_svg(s: dict) -> None:
  parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="880" viewBox="0 0 1280 880">',
    '<style>text{font-family:Arial,sans-serif;fill:#183041}.muted{fill:#526977}.grid{stroke:#dce5e9;stroke-width:1}</style>',
    '<rect width="1280" height="880" fill="#f3f6f8"/>']
  def text(x,y,value,size=16,extra=''):
    parts.append(f'<text x="{x}" y="{y}" font-size="{size}" {extra}>{escape(str(value))}</text>')
  def rect(x,y,w,h,color,extra=''):
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}" {extra}/>')
  text(40,48,'THE PAVILIA FARM III',28,'font-weight="bold"')
  text(40,77,f"Contract register | PASP {s['pasp_date_min']} to {s['pasp_date_max']} | Source submitted 2026-06-26",16,'class="muted"')
  cards=[('Contract records',f"{s['transactions']:,}"),('ASP signed',s['status_counts']['asp_signed']),
         ('Terminated / all records',f"{s['termination_rate_pct']:.2f}%"),
         ('Mean price / ASP signed',f"HK$ {s['asp_signed_avg_price_hkd']/1e6:.2f}M")]
  for i,(label,value) in enumerate(cards):
    x=40+i*305;rect(x,102,285,95,'white', 'rx="8"');text(x+18,133,label,15,'class="muted"');text(x+18,173,value,30,'font-weight="bold"')
  rect(40,218,1200,285,'white','rx="8"')
  text(62,248,'Monthly contract records by PASP date',19,'font-weight="bold"')
  counts=list(s['monthly_contract_counts'].values());labels=list(s['monthly_contract_counts'])
  high=((max(counts)//200)+1)*200
  for value in range(0,high+1,200):
    y=450-value/high*165
    parts.append(f'<path d="M105 {y} H1200" class="grid"/>');text(64,y+5,value,13,'class="muted"')
  points=[(105+i/(len(counts)-1)*1095,450-n/high*165) for i,n in enumerate(counts)]
  parts.append('<polyline fill="none" stroke="#147b91" stroke-width="3" points="'+' '.join(f'{x:.1f},{y:.1f}' for x,y in points)+'"/>')
  for i,label in enumerate(labels):
    if i%12==0 or i==len(labels)-1:
      text(points[i][0]-25,477,label,13,'class="muted"')
    if counts[i]>100:
      text(points[i][0]-110 if i>len(labels)-10 else points[i][0]+7,points[i][1]-9,f'{label}: {counts[i]}',13)
  rect(40,525,590,265,'white','rx="8"');rect(650,525,590,265,'white','rx="8"')
  text(62,557,'Mean contract price by block',19,'font-weight="bold"')
  text(62,580,'ASP signed only, latest revised price (HK$ million)',14,'class="muted"')
  blocks=s['asp_signed_block_avg_price_hkd']
  for i,(name,value) in enumerate(blocks.items()):
    y=605+i*40;text(62,y+18,name,14);rect(180,y,315*value/20e6,25,'#147b91');text(190+315*value/20e6,y+18,f'{value/1e6:.2f}',14)
  text(672,557,'Latest effective payment plan',19,'font-weight="bold"')
  text(672,580,'All contract records, including terminated contracts',14,'class="muted"')
  for i,(name,value) in enumerate(s['latest_payment_counts'].items()):
    y=609+i*47;text(672,y+16,name,14);rect(835,y,270*value/s['transactions'],25,['#147b91','#d98d3b','#8c9aa3'][i%3]);text(845+270*value/s['transactions'],y+18,value,14)
  text(40,822,f"Status: {s['status_counts']['asp_signed']} ASP signed, {s['status_counts']['terminated']} terminated, {s['status_counts']['pasp_only']} PASP only. Counts are contracts, not unique units.",14)
  text(40,849,'7 PASP-only records explicitly did not proceed further. 7 payment plans remain Unmapped. Source date anomaly retained.',13,'class="muted"')
  parts.append('</svg>')
  (ROOT / 'visualize/dashboard.svg').write_text('\n'.join(parts),encoding='utf-8')


if __name__ == '__main__':
  parser=argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--png',action='store_true',help='Render the SVG to PNG using installed Playwright Chromium')
  args=parser.parse_args()
  result=build_report()
  print(json.dumps({k:v for k,v in result.items() if k != 'monthly_contract_counts'},indent=2))
  if args.png:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
      browser=playwright.chromium.launch(headless=True, timeout=15000)
      page=browser.new_page(viewport={'width':1280,'height':880},device_scale_factor=1.5)
      page.set_content('<style>body{margin:0}</style>'+ (ROOT / 'visualize/dashboard.svg').read_text(encoding='utf-8'))
      page.screenshot(path=str(ROOT / 'visualize/dashboard.png'))
      browser.close()
