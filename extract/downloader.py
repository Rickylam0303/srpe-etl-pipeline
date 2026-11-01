"""PDF download helpers and registration of successfully parsed local files."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from extract.ingestion_log import IngestionLog, IngestionRecord


@dataclass
class DownloadResult:
  local_path: Path
  skipped: bool
  development_name: str
  file_name: str


def download_pdf_with_retry(
  url: str,
  dest_path: Path,
  retries: int = 3,
  backoff_seconds: float = 2.0,
) -> tuple[Path, str | None, str | None]:
  """Download a PDF and return (path, last_modified, error_message)."""
  dest_path.parent.mkdir(parents=True, exist_ok=True)
  last_error: str | None = None

  for attempt in range(1, retries + 1):
    try:
      with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        response = client.get(
          url,
          headers={"User-Agent": "SRPE-ETL-Portfolio/0.1 (educational project)"},
        )
        response.raise_for_status()
        dest_path.write_bytes(response.content)
        last_modified = response.headers.get("Last-Modified")
        return dest_path, last_modified, None
    except httpx.HTTPError as exc:
      last_error = str(exc)
      if attempt < retries:
        time.sleep(backoff_seconds * attempt)

  raise RuntimeError(f"Failed to download {url} after {retries} attempts: {last_error}")


def register_local_pdf(
  pdf_path: Path,
  ingestion_log: IngestionLog,
  development_name: str,
  pdf_url: str | None = None,
  server_last_modified: str | None = None,
) -> DownloadResult:
  """Record a manually downloaded PDF in the ingestion log."""
  pdf_path = Path(pdf_path)
  file_name = pdf_path.name
  file_hash = IngestionLog.file_hash(pdf_path)
  latest = ingestion_log.get_latest(development_name, file_name)
  if latest and latest.file_hash == file_hash:
    pdf_url = pdf_url or latest.pdf_url
    server_last_modified = server_last_modified or latest.server_last_modified

  import pdfplumber

  with pdfplumber.open(pdf_path) as pdf:
    page_count = len(pdf.pages)

  ingestion_log.log(
    IngestionRecord(
      development_name=development_name,
      file_name=file_name,
      pdf_url=pdf_url,
      server_last_modified=server_last_modified,
      file_hash=file_hash,
      status="extracted",
      page_count=page_count,
      ingested_at=IngestionLog.now_iso(),
      error_message=None,
    )
  )

  return DownloadResult(
    local_path=pdf_path,
    skipped=False,
    development_name=development_name,
    file_name=file_name,
  )
