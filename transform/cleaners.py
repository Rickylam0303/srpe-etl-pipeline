"""Type cleaning helpers for HK SRPE staging data."""

from __future__ import annotations

import re
from datetime import date, datetime

DATE_INPUT_FORMAT = "%d/%m/%Y"
PRICE_PATTERN = re.compile(r"^\$?\s*(\d{1,3}(?:,\d{3})+|\d+)\s*$")
REVISED_PRICE_PATTERN = re.compile(
  r"(?:更改為|adjusted to)\s*\$?([\d,]+)",
  re.IGNORECASE,
)


def _as_optional_text(value: str | float | None) -> str | None:
  if value is None:
    return None
  text = str(value).strip()
  if not text or text.lower() in {'nan', 'none', '<na>', 'nat'}:
    return None
  return text


def parse_price_hkd(value: str | None) -> int | None:
  text = _as_optional_text(value)
  if not text:
    return None
  match = PRICE_PATTERN.fullmatch(text)
  if not match:
    return None
  price = int(match.group(1).replace(",", ""))
  return price if price > 0 else None


def parse_revised_price_hkd(price_revision_raw: str | None) -> int | None:
  text = _as_optional_text(price_revision_raw)
  if not text:
    return None
  events = re.findall(
    r'On\s+([^\s,，]+)[,，]?\s+the price\s+adjusted to\s*\$?([\d,]+)', text, re.I)
  english_count = len(re.findall(r'\bthe price\s+adjusted to', text, re.I))
  if english_count and len(events) != english_count:
    raise ValueError('price_revision_date_unresolved')
  if not english_count:
    events = re.findall(r'在\s*([^\s,，]+)[,，].*?更改為\s*\$?([\d,]+)', text, re.I)
    if len(events) != len(re.findall('更改為', text)):
      raise ValueError('price_revision_date_unresolved')
  if not events:
    raise ValueError('price_revision_date_unresolved')
  dated = {}
  for token, amount in events:
    amended_on, price = parse_hk_date(token), parse_price_hkd(amount)
    if amended_on is None or price is None:
      raise ValueError('invalid_price_revision')
    if amended_on in dated and dated[amended_on] != price:
      raise ValueError('conflicting_price_revision')
    dated[amended_on] = price
  return dated[max(dated)]


def parse_hk_date(value: str | None) -> date | None:
  text = _as_optional_text(value)
  if not text:
    return None
  if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", text):
    return None
  try:
    return datetime.strptime(text, DATE_INPUT_FORMAT).date()
  except ValueError:
    return None


def normalize_block_name(value: str | None) -> str | None:
  text = _as_optional_text(value)
  if not text:
    return None
  cleaned = re.sub(r"\s+", " ", text)
  return cleaned or None


def normalize_identifier(value) -> str | None:
  text = _as_optional_text(value)
  if text and re.fullmatch(r'\d+\.0', text):
    return text[:-2]
  return text


def derive_transaction_status(
  *,
  termination_date: date | None,
  asp_date: date | None,
  pasp_date: date | None,
) -> str:
  if termination_date:
    return "terminated"
  if asp_date:
    return "asp_signed"
  if pasp_date:
    return "pasp_only"
  return "unknown"


def build_natural_key(
  *,
  development_name: str,
  block_name: str | None,
  floor: str | None,
  unit: str | None,
  pasp_date: date | None,
) -> str:
  pasp_token = pasp_date.isoformat() if pasp_date else "unknown-date"
  return "|".join(
    [
      str(development_name).strip(),
      str(block_name or "").strip(),
      str(floor or "").strip(),
      str(unit or "").strip(),
      pasp_token,
    ]
  )
