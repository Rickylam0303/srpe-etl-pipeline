"""Parse Hong Kong SRPE Register of Transactions PDFs with pdfplumber."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import pdfplumber

DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")

# Part 1 metadata (page 1)
PHASE_NAME_PATTERN = re.compile(
  r"Name of the Phase\s+(.+?)\s+Phase No\.",
  re.DOTALL,
)
PHASE_NAME_FALLBACK = re.compile(
  r"THE PAVILIA FARM III|Phase No\.\s*\(if any\)\s+(.+)",
)
LOCATION_PATTERN = re.compile(
  r"Location of the Phase\s+(.+?)(?:\s+重要告示|\s+Important Note)",
  re.DOTALL,
)


class ExtractionQualityError(ValueError):
  """The source contains transactions that could not be reconciled."""


def _effective_page(page):
  """Exclude date tokens explicitly struck through in the source document."""
  struck = []
  lines = [e for e in page.edges if e['orientation'] == 'h' and e['x1'] - e['x0'] > 15]
  for word in page.extract_words():
    if DATE_PATTERN.fullmatch(word['text']) and any(
      word['top'] + 1 < line['top'] < word['bottom'] - 1
      and line['x0'] <= word['x0'] + 1 and line['x1'] >= word['x1'] - 1
      for line in lines
    ):
      struck.append(word)
  if not struck:
    return page, []
  def keep(obj):
    if obj.get('object_type') != 'char':
      return True
    return not any(w['x0'] - .1 <= obj['x0'] <= w['x1']
                   and w['top'] - .1 <= obj['top'] <= w['bottom'] for w in struck)
  return page.filter(keep), [word['text'] for word in struck]


def _candidate_count(page, text: str) -> int:
  xs = []
  for x in sorted(e['x0'] for e in page.edges
                  if e['orientation'] == 'v' and e['bottom'] - e['top'] > 40):
    if not xs or x - xs[-1] > 2:
      xs.append(x)
  if len(xs) >= 2:
    return sum(bool(DATE_PATTERN.fullmatch(w['text'])) for w in page.extract_words()
               if xs[0] - 1 <= w['x0'] and w['x1'] <= xs[1] + 1)
  return len(re.findall(r'(?m)^\d{2}/\d{2}/\d{4}(?=\s)', text))


def _open_table_fallback(page) -> list:
  """Close an otherwise ruled table whose bottom border is missing.

  Some SRPE rows extend beyond the declared MediaBox. Use the actual rule
  endpoints, not a guessed row height or development-specific column offsets.
  Only use this for pages where the ordinary table extractor found no rows.
  """
  verticals = [e for e in page.edges if e['orientation'] == 'v'
               and e['bottom'] - e['top'] > 40]
  boundaries = []
  for x in sorted(e['x0'] for e in verticals):
    if not boundaries or x - boundaries[-1] > 2:
      boundaries.append(x)
  if len(boundaries) != 12:  # eleven SRPE transaction columns
    return []
  top = min(e['top'] for e in verticals)
  bottom = max(e['bottom'] for e in verticals)
  if any(abs(e['bottom'] - bottom) > 2 for e in verticals):
    return []
  expanded = page.crop((page.bbox[0], page.bbox[1], page.bbox[2],
                        max(page.bbox[3], bottom + 1)), strict=False)
  return expanded.extract_tables({
    'vertical_strategy': 'explicit', 'explicit_vertical_lines': boundaries,
    'horizontal_strategy': 'explicit', 'explicit_horizontal_lines': [top, bottom],
  })


@dataclass
class DevelopmentInfo:
  development_name_en: str
  development_name_tc: str | None
  phase_label: str | None
  location_en: str | None
  location_tc: str | None
  source_pdf: str


@dataclass
class RawTransaction:
  development_name_en: str
  pasp_date: str
  asp_date: str | None
  termination_date: str | None
  block_name: str
  floor: str
  unit: str
  parking: str | None
  price_raw: str
  price_revision_raw: str | None
  payment_terms_raw: str | None
  related_party_raw: str | None
  source_pdf: str
  source_page: int


def _clean(value: str | None) -> str | None:
  if value is None:
    return None
  cleaned = value.replace("\u00a0", " ").replace("(cid:9)", " ")
  cleaned = re.sub(r"\s+", " ", cleaned).strip()
  return cleaned or None


def _split_bilingual(value: str | None) -> tuple[str | None, str | None]:
  """Split '中文\\nEnglish' fields into (tc, en) where possible."""
  if not value:
    return None, None
  parts = [part.strip() for part in value.split("\n") if part.strip()]
  if len(parts) >= 2:
    return parts[0], parts[-1]
  return parts[0], None


def _is_transaction_row(row: list[str | None]) -> bool:
  if not row or not row[0]:
    return False
  first = _clean(row[0])
  return bool(first and DATE_PATTERN.match(first))


def _parse_development_from_text(text: str, pdf_name: str) -> DevelopmentInfo:
  text = text.replace("(cid:9)", " ")

  development_name_en = "UNKNOWN"
  match = PHASE_NAME_PATTERN.search(text)
  if match:
    development_name_en = _clean(match.group(1)) or development_name_en
  else:
    # Fallback: look for English name on line after 期數名稱
    for line in text.splitlines():
      if "THE PAVILIA" in line or re.search(r"^[A-Z][A-Z0-9 \-']+$", line.strip()):
        candidate = _clean(line)
        if candidate and "Register of Transactions" not in candidate:
          development_name_en = candidate
          break

  phase_label = None
  phase_match = re.search(r"Phase No\.\s*\(if any\)\s+(.+)", text)
  if phase_match:
    phase_label = _clean(phase_match.group(1))

  development_name_tc = None
  tc_match = re.search(r"期數名稱\s+(.+?)\s+期數", text)
  if tc_match:
    development_name_tc = _clean(tc_match.group(1))

  location_en = None
  location_tc = None
  loc_match = LOCATION_PATTERN.search(text)
  if loc_match:
    location_en = _clean(loc_match.group(1))
  tc_location = re.search(r"期數位置\s+(.+?)(?:\n|Location of the Phase)", text)
  if tc_location:
    location_tc = _clean(tc_location.group(1))

  return DevelopmentInfo(
    development_name_en=development_name_en,
    development_name_tc=development_name_tc,
    phase_label=phase_label,
    location_en=location_en,
    location_tc=location_tc,
    source_pdf=pdf_name,
  )


def _parse_transaction_row(
  row: list[str | None],
  development_name_en: str,
  pdf_name: str,
  page_number: int,
) -> RawTransaction:
  cells = [(_clean(cell) or "") for cell in row]
  while len(cells) < 11:
    cells.append("")

  block_tc, block_en = _split_bilingual(row[3] if len(row) > 3 else None)
  block_name = _clean(block_en or block_tc) or cells[3]

  return RawTransaction(
    development_name_en=development_name_en,
    pasp_date=cells[0],
    asp_date=cells[1] or None,
    termination_date=cells[2] or None,
    block_name=block_name,
    floor=cells[4],
    unit=cells[5],
    parking=cells[6] or None,
    price_raw=cells[7],
    price_revision_raw=cells[8] or None,
    payment_terms_raw=cells[9] or None,
    related_party_raw=cells[10] or None,
    source_pdf=pdf_name,
    source_page=page_number,
  )


def parse_register_pdf(
  pdf_path: Path, *, report_path: Path | None = None,
) -> tuple[DevelopmentInfo, list[RawTransaction]]:
  """Extract development metadata and raw transaction rows from one SRPE PDF."""
  pdf_path = Path(pdf_path)
  pdf_name = pdf_path.name
  transactions: list[RawTransaction] = []
  report = {'source_pdf': pdf_name, 'sha256': hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
            'pages': [], 'issues': [], 'status': 'failed'}
  development = DevelopmentInfo(
    development_name_en="UNKNOWN",
    development_name_tc=None,
    phase_label=None,
    location_en=None,
    location_tc=None,
    source_pdf=pdf_name,
  )

  with pdfplumber.open(pdf_path) as pdf:
    first_page_text = (pdf.pages[0].extract_text() or '') if pdf.pages else ''
    development = _parse_development_from_text(first_page_text, pdf_name)

    for page_index, page in enumerate(pdf.pages[1:], start=2):
      page, struck_dates = _effective_page(page)
      text = page.extract_text() or ''
      candidates = _candidate_count(page, text)
      tables = page.extract_tables() or []
      rows = [row for table in tables for row in table if _is_transaction_row(row)]
      fallback = False
      if candidates and not rows:
        fallback = True
        tables = _open_table_fallback(page)
        rows = [row for table in tables for row in table if _is_transaction_row(row)]
      for row in rows:
        transactions.append(_parse_transaction_row(
          row, development.development_name_en, pdf_name, page_index))
      if candidates or rows:
        report['pages'].append({'source_page': page_index, 'candidate_rows': candidates,
                                'parsed_rows': len(rows), 'fallback': fallback,
                                'struck_dates_excluded': struck_dates})
      if candidates != len(rows):
        report['issues'].append({'source_page': page_index, 'reason': 'row_count_mismatch',
                                 'candidate_rows': candidates, 'parsed_rows': len(rows)})
    report['page_count'] = len(pdf.pages)

  if not transactions:
    report['issues'].append({'reason': 'no_transactions'})
  if development.development_name_en == 'UNKNOWN':
    report['issues'].append({'reason': 'unknown_development'})
  identities = [(r.development_name_en, r.block_name, r.floor, r.unit, r.pasp_date)
                for r in transactions]
  if len(identities) != len(set(identities)):
    report['issues'].append({'reason': 'duplicate_transaction_identity'})
  report['transaction_count'] = len(transactions)
  report['status'] = 'failed' if report['issues'] else 'passed'
  if report_path:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
  if report['issues']:
    raise ExtractionQualityError(f"PDF reconciliation failed: {report['issues']}; report={report_path}")
  return development, transactions


def write_staging_csv(
  development: DevelopmentInfo,
  transactions: list[RawTransaction],
  output_dir: Path,
) -> tuple[Path, Path]:
  """Write raw extracted rows to CSV for the Transform layer."""
  output_dir.mkdir(parents=True, exist_ok=True)
  safe_name = re.sub(r"[^\w\-]+", "_", development.development_name_en)

  dev_path = output_dir / f"{safe_name}_development.csv"
  tx_path = output_dir / f"{safe_name}_transactions_raw.csv"

  with dev_path.open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(asdict(development).keys()))
    writer.writeheader()
    writer.writerow(asdict(development))

  with tx_path.open("w", encoding="utf-8-sig", newline="") as handle:
    fieldnames = list(asdict(transactions[0]).keys()) if transactions else list(RawTransaction.__dataclass_fields__)
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    writer.writeheader()
    for tx in transactions:
      writer.writerow(asdict(tx))

  return dev_path, tx_path
