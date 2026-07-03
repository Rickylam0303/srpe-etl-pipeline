"""Parse Hong Kong SRPE Register of Transactions PDFs with pdfplumber."""

from __future__ import annotations

import csv
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
    loc_raw = loc_match.group(1).strip()
    location_tc, location_en = _split_bilingual(loc_raw)

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


def parse_register_pdf(pdf_path: Path) -> tuple[DevelopmentInfo, list[RawTransaction]]:
  """Extract development metadata and raw transaction rows from one SRPE PDF."""
  pdf_path = Path(pdf_path)
  pdf_name = pdf_path.name
  transactions: list[RawTransaction] = []
  development = DevelopmentInfo(
    development_name_en="UNKNOWN",
    development_name_tc=None,
    phase_label=None,
    location_en=None,
    location_tc=None,
    source_pdf=pdf_name,
  )

  with pdfplumber.open(pdf_path) as pdf:
    if not pdf.pages:
      return development, transactions

    first_page_text = pdf.pages[0].extract_text() or ""
    development = _parse_development_from_text(first_page_text, pdf_name)

    for page_index, page in enumerate(pdf.pages[1:], start=2):
      page_rows = 0
      for table in page.extract_tables() or []:
        for row in table:
          if not _is_transaction_row(row):
            continue
          page_rows += 1
          transactions.append(
            _parse_transaction_row(
              row,
              development.development_name_en,
              pdf_name,
              page_index,
            )
          )
      if page_rows == 0:
        text = page.extract_text() or ""
        if re.search(r"\d{2}/\d{2}/\d{4}", text):
          print(f"Warning: page {page_index} has dates in text but no parsed table rows.")

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
