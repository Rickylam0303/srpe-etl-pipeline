"""Bilingual payment-term mapping for HK SRPE records."""

from __future__ import annotations

import re

from transform.cleaners import parse_hk_date

# First match wins. Patterns are applied to lowercase normalized text.
PAYMENT_RULES: list[tuple[re.Pattern[str], str]] = [
  (re.compile(r"stage\s*payment|建築期付款|建築期付款計劃", re.IGNORECASE), "Stage Payment"),
  (re.compile(r"\d+\s*天現金|day[- ]?cash\s*payment", re.IGNORECASE), "Cash Payment Plan"),
  (re.compile(r"即供|immediate\s*payment", re.IGNORECASE), "Immediate Payment"),
  (re.compile(r"按揭|mortgage", re.IGNORECASE), "Mortgage"),
]

PAYMENT_METHOD_PATTERN = re.compile(
  r"付款方法[:：]\s*(.+?)(?:terms of payment|$)",
  re.IGNORECASE,
)


def _normalize_payment_text(value: str | None) -> str:
  if value is None:
    return ""
  text = str(value).strip()
  if not text or text.lower() == "nan":
    return ""
  text = text.replace("\n", " ")
  text = re.sub(r"\s+", " ", text).strip().lower()
  return text


def _latest_payment_section(payment_terms_raw: str | None) -> str:
  """Select the last dated amendment, independent of the order in the PDF."""
  text = _normalize_payment_text(payment_terms_raw)
  if not text:
    return ''
  markers = list(re.finditer(
    r'on\s+([^\s,，]+)[,，]?\s+the terms of payment adjusted to', text, re.I))
  english_count = text.count('the terms of payment adjusted to')
  if english_count and len(markers) != english_count:
    raise ValueError('payment_revision_date_unresolved')
  if not english_count:
    markers = list(re.finditer(r'在\s*([^\s,，]+)[,，]\s*支付條款更改為', text))
    if len(markers) != text.count('支付條款更改為'):
      raise ValueError('payment_revision_date_unresolved')
  if not markers:
    if 'payment adjusted to' in text or '支付條款更改為' in text:
      raise ValueError('payment_revision_date_unresolved')
    return text
  dated = {}
  for index, marker in enumerate(markers):
    amended_on = parse_hk_date(marker.group(1))
    if amended_on is None:
      raise ValueError('invalid_payment_revision_date')
    end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
    section = text[marker.end():end].strip()
    primary = _primary_text(section)
    if not primary:
      raise ValueError('missing_revised_payment_terms')
    if amended_on in dated and _primary_text(dated[amended_on]) != primary:
      raise ValueError('conflicting_payment_revision')
    dated[amended_on] = section
  return dated[max(dated)]


def _primary_text(text: str) -> str:

  match = PAYMENT_METHOD_PATTERN.search(text)
  if match:
    return match.group(1).strip()

  return text.split(" terms of payment", maxsplit=1)[0].strip()


def extract_primary_payment_text(payment_terms_raw: str | None) -> str:
  """Latest effective payment method; full source history remains untouched."""
  return _primary_text(_latest_payment_section(payment_terms_raw))


def map_payment_category(payment_terms_raw: str | None) -> str:
  primary_text = extract_primary_payment_text(payment_terms_raw)
  normalized = _normalize_payment_text(primary_text or payment_terms_raw)

  for pattern, category in PAYMENT_RULES:
    if pattern.search(normalized):
      return category

  return "Unmapped"
