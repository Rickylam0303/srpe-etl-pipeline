"""SQLite ingestion log for SRPE PDF downloads.

Tracks which PDFs were already downloaded so the pipeline only fetches new or
updated files (by server Last-Modified header and file hash).
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

IngestionStatus = Literal["downloaded", "skipped", "failed", "extracted"]


@dataclass
class IngestionRecord:
    development_name: str
    file_name: str
    pdf_url: str | None
    server_last_modified: str | None
    file_hash: str | None
    status: IngestionStatus
    page_count: int | None
    ingested_at: str
    error_message: str | None = None


class IngestionLog:
  def __init__(self, db_path: Path) -> None:
    self.db_path = db_path
    self.db_path.parent.mkdir(parents=True, exist_ok=True)
    self._init_db()

  def _connect(self) -> sqlite3.Connection:
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    return conn

  def _init_db(self) -> None:
    with self._connect() as conn:
      conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ingestion_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          development_name TEXT NOT NULL,
          file_name TEXT NOT NULL,
          pdf_url TEXT,
          server_last_modified TEXT,
          file_hash TEXT,
          status TEXT NOT NULL,
          page_count INTEGER,
          ingested_at TEXT NOT NULL,
          error_message TEXT,
          UNIQUE(development_name, file_name)
        )
        """
      )
      conn.commit()

  @staticmethod
  def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
      for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()

  def get_latest(self, development_name: str, file_name: str) -> IngestionRecord | None:
    with self._connect() as conn:
      row = conn.execute(
        """
        SELECT development_name, file_name, pdf_url, server_last_modified,
               file_hash, status, page_count, ingested_at, error_message
        FROM ingestion_log
        WHERE development_name = ? AND file_name = ?
        ORDER BY ingested_at DESC
        LIMIT 1
        """,
        (development_name, file_name),
      ).fetchone()

    if row is None:
      return None

    return IngestionRecord(**dict(row))

  def should_download(
    self,
    development_name: str,
    file_name: str,
    server_last_modified: str | None,
    file_hash: str | None,
  ) -> bool:
    """Return True if the remote PDF is new or changed."""
    latest = self.get_latest(development_name, file_name)
    if latest is None:
      return True
    if file_hash and latest.file_hash and file_hash != latest.file_hash:
      return True
    if server_last_modified and latest.server_last_modified:
      return server_last_modified > latest.server_last_modified
    return latest.status == "failed"

  def log(self, record: IngestionRecord) -> None:
    with self._connect() as conn:
      conn.execute(
        """
        INSERT INTO ingestion_log (
          development_name, file_name, pdf_url, server_last_modified,
          file_hash, status, page_count, ingested_at, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(development_name, file_name) DO UPDATE SET
          pdf_url = excluded.pdf_url,
          server_last_modified = excluded.server_last_modified,
          file_hash = excluded.file_hash,
          status = excluded.status,
          page_count = excluded.page_count,
          ingested_at = excluded.ingested_at,
          error_message = excluded.error_message
        """,
        (
          record.development_name,
          record.file_name,
          record.pdf_url,
          record.server_last_modified,
          record.file_hash,
          record.status,
          record.page_count,
          record.ingested_at,
          record.error_message,
        ),
      )
      conn.commit()

  @staticmethod
  def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
