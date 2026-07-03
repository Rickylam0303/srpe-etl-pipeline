"""Bilingual payment-term mapping for HK SRPE records."""

from __future__ import annotations

import re

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


def extract_primary_payment_text(payment_terms_raw: str | None) -> str:
  """Keep the first payment method line instead of the full discount bundle."""
  text = _normalize_payment_text(payment_terms_raw)
  if not text:
    return ""

  match = PAYMENT_METHOD_PATTERN.search(text)
  if match:
    return match.group(1).strip()

  return text.split(" terms of payment", maxsplit=1)[0].strip()


def map_payment_category(payment_terms_raw: str | None) -> str:
  primary_text = extract_primary_payment_text(payment_terms_raw)
  normalized = _normalize_payment_text(primary_text or payment_terms_raw)

  for pattern, category in PAYMENT_RULES:
    if pattern.search(normalized):
      return category

  return "Unmapped"
