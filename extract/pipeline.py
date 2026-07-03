"""Extract pipeline orchestration: download -> parse -> staging CSV -> ingestion log."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from extract.downloader import download_pdf_with_retry, register_local_pdf
from extract.ingestion_log import IngestionLog, IngestionRecord
from extract.pdf_parser import parse_register_pdf, write_staging_csv
from extract.srpe_client import DevelopmentSummary, RegisterOfTransactionsFile, SrpeClient


@dataclass
class ExtractResult:
  development_name: str
  pdf_path: Path
  transaction_count: int
  development_csv: Path
  transactions_csv: Path
  skipped_download: bool


def load_settings(config_path: Path) -> dict:
  with config_path.open(encoding="utf-8") as handle:
    return yaml.safe_load(handle)


def extract_local_pdf(
  pdf_path: Path,
  *,
  staging_dir: Path,
  ingestion_log: IngestionLog,
) -> ExtractResult:
  development, transactions = parse_register_pdf(pdf_path)
  dev_csv, tx_csv = write_staging_csv(development, transactions, staging_dir)
  register_local_pdf(
    pdf_path=pdf_path,
    ingestion_log=ingestion_log,
    development_name=development.development_name_en,
  )
  return ExtractResult(
    development_name=development.development_name_en,
    pdf_path=pdf_path,
    transaction_count=len(transactions),
    development_csv=dev_csv,
    transactions_csv=tx_csv,
    skipped_download=False,
  )


def _should_skip_download(
  ingestion_log: IngestionLog,
  development_name: str,
  file_name: str,
  server_last_modified: str | None,
  file_hash: str | None,
) -> bool:
  return not ingestion_log.should_download(
    development_name,
    file_name,
    server_last_modified,
    file_hash,
  )


def extract_from_srpe_development(
  dev_id: str,
  *,
  raw_pdf_dir: Path,
  staging_dir: Path,
  ingestion_log: IngestionLog,
  settings: dict,
) -> ExtractResult:
  extract_cfg = settings["extract"]
  srpe_cfg = settings["srpe"]

  with SrpeClient(
    language=extract_cfg.get("default_language", "en"),
    user_agent=srpe_cfg.get("user_agent", "SRPE-ETL-Portfolio/0.1"),
    timeout_seconds=extract_cfg.get("request_timeout_seconds", 60),
  ) as client:
    client.bootstrap_session()
    register_file = client.get_register_of_transactions_file(dev_id)
    if register_file is None:
      raise RuntimeError(f"No Register of Transactions PDF found for devId={dev_id}")

    development_name = _development_label(register_file, client, dev_id)
    latest = ingestion_log.get_latest(development_name, register_file.file_name)
    if latest and not ingestion_log.should_download(
      development_name,
      register_file.file_name,
      register_file.submission_time,
      latest.file_hash,
    ):
      existing_pdf = raw_pdf_dir / register_file.file_name
      if existing_pdf.exists():
        return extract_local_pdf(
          existing_pdf,
          staging_dir=staging_dir,
          ingestion_log=ingestion_log,
        )

    pdf_path = raw_pdf_dir / register_file.file_name
    client.download_register_pdf(register_file, pdf_path)

  file_hash = IngestionLog.file_hash(pdf_path)
  ingestion_log.log(
    IngestionRecord(
      development_name=development_name,
      file_name=register_file.file_name,
      pdf_url=register_file.download_url,
      server_last_modified=register_file.submission_time,
      file_hash=file_hash,
      status="downloaded",
      page_count=None,
      ingested_at=IngestionLog.now_iso(),
      error_message=None,
    )
  )

  result = extract_local_pdf(
    pdf_path,
    staging_dir=staging_dir,
    ingestion_log=ingestion_log,
  )
  result.skipped_download = False
  return result


def extract_from_srpe_search(
  search_name: str,
  *,
  raw_pdf_dir: Path,
  staging_dir: Path,
  ingestion_log: IngestionLog,
  settings: dict,
  limit: int | None = None,
) -> list[ExtractResult]:
  extract_cfg = settings["extract"]
  srpe_cfg = settings["srpe"]
  delay_seconds = float(extract_cfg.get("request_delay_seconds", 1.0))
  results: list[ExtractResult] = []

  with SrpeClient(
    language=extract_cfg.get("default_language", "en"),
    user_agent=srpe_cfg.get("user_agent", "SRPE-ETL-Portfolio/0.1"),
    timeout_seconds=extract_cfg.get("request_timeout_seconds", 60),
  ) as client:
    client.bootstrap_session()
    matches = client.search_developments_by_name(search_name)
    if limit is not None:
      matches = matches[:limit]

    for match in matches:
      try:
        results.append(
          extract_from_srpe_development(
            match.dev_id,
            raw_pdf_dir=raw_pdf_dir,
            staging_dir=staging_dir,
            ingestion_log=ingestion_log,
            settings=settings,
          )
        )
      except Exception as exc:
        ingestion_log.log(
          IngestionRecord(
            development_name=_summary_label(match),
            file_name=f"dev_{match.dev_id}.pdf",
            pdf_url=None,
            server_last_modified=None,
            file_hash=None,
            status="failed",
            page_count=None,
            ingested_at=IngestionLog.now_iso(),
            error_message=str(exc),
          )
        )
      time.sleep(delay_seconds)

  return results


def _development_label(
  register_file: RegisterOfTransactionsFile,
  client: SrpeClient,
  dev_id: str,
) -> str:
  detail = client.get_selected_development(dev_id)
  dev_info = detail.get("devInfoResp") or detail
  dev = dev_info.get("dev") or {}
  return (
    dev.get("engPhaseName")
    or dev.get("engName")
    or dev.get("chnPhaseName")
    or dev.get("chnName")
    or register_file.file_name
  )


def _summary_label(summary: DevelopmentSummary) -> str:
  return summary.eng_phase_name or summary.eng_name or summary.chn_phase_name or summary.chn_name or summary.dev_id
