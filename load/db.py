"""PostgreSQL connection helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass

import psycopg


@dataclass
class DatabaseConfig:
  host: str
  port: int
  name: str
  user: str
  password: str

  @classmethod
  def from_settings(cls, settings: dict) -> DatabaseConfig:
    db = settings.get("database", {})
    return cls(
      host=os.getenv("SRPE_DB_HOST", db.get("host", "localhost")),
      port=int(os.getenv("SRPE_DB_PORT", db.get("port", 5432))),
      name=os.getenv("SRPE_DB_NAME", db.get("name", "srpe_etl")),
      user=os.getenv("SRPE_DB_USER", ""),
      password=os.getenv("SRPE_DB_PASSWORD", ""),
    )

  def conninfo(self) -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
      return database_url
    if not self.user:
      raise ValueError(
        "Database user not set. Export SRPE_DB_USER and SRPE_DB_PASSWORD, or set DATABASE_URL."
      )
    return (
      f"host={self.host} port={self.port} dbname={self.name} "
      f"user={self.user} password={self.password}"
    )


def connect(settings: dict) -> psycopg.Connection:
  config = DatabaseConfig.from_settings(settings)
  return psycopg.connect(config.conninfo())


def init_schema(settings: dict, schema_path) -> None:
  sql = schema_path.read_text(encoding="utf-8")
  with connect(settings) as conn:
    with conn.cursor() as cur:
      cur.execute(sql)
    conn.commit()


def init_views(settings: dict, views_path) -> None:
  sql = views_path.read_text(encoding="utf-8")
  with connect(settings) as conn:
    with conn.cursor() as cur:
      cur.execute(sql)
    conn.commit()


def ensure_database(settings: dict) -> None:
  """Create the target database if it does not exist yet."""
  config = DatabaseConfig.from_settings(settings)
  if not config.user:
    raise ValueError(
      "Database user not set. Export SRPE_DB_USER and SRPE_DB_PASSWORD, or set DATABASE_URL."
    )
  if not config.password:
    raise ValueError(
      "Database password not set. Edit .env and set SRPE_DB_PASSWORD, then rerun setup_load.ps1."
    )

  maintenance_conninfo = (
    f"host={config.host} port={config.port} dbname=postgres "
    f"user={config.user} password={config.password}"
  )
  with psycopg.connect(maintenance_conninfo, autocommit=True) as conn:
    with conn.cursor() as cur:
      cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (config.name,))
      if cur.fetchone():
        return
      cur.execute(f'CREATE DATABASE "{config.name}"')
