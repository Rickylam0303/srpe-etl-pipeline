"""Type cleaning helpers for HK SRPE staging data."""

from __future__ import annotations

import re
from datetime import date, datetime

DATE_INPUT_FORMAT = "%d/%m/%Y"
PRICE_PATTERN = re.compile(r"[\d,]+")
REVISED_PRICE_PATTERN = re.compile(
  r"(?:更改為|adjusted to)\s*\$?([\d,]+)",
  re.IGNORECASE,
)


def _as_optional_text(value: str | float | None) -> str | None:
  if value is None:
    return None
  text = str(value).strip()
  if not text or text.lower() == "nan":
    return None
  return text


def parse_price_hkd(value: str | None) -> int | None:
  text = _as_optional_text(value)
  if not text:
    return None
  match = PRICE_PATTERN.search(text.replace("$", ""))
  if not match:
    return None
  return int(match.group(0).replace(",", ""))


def parse_revised_price_hkd(price_revision_raw: str | None) -> int | None:
  text = _as_optional_text(price_revision_raw)
  if not text:
    return None
  match = REVISED_PRICE_PATTERN.search(text)
  if not match:
    return None
  return int(match.group(1).replace(",", ""))


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
  if not value:
    return None
  cleaned = re.sub(r"\s+", " ", value.strip())
  return cleaned or None


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
