"""CLI entrypoint for the Load layer."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml
from dotenv import load_dotenv

from load.db import connect, ensure_database, init_schema, init_views
from load.loader import load_all_transformed_files, load_transformed_csv


def load_settings(config_path: Path) -> dict:
  with config_path.open(encoding="utf-8") as handle:
    return yaml.safe_load(handle)


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description="SRPE Load layer (PostgreSQL UPSERT)")
  parser.add_argument(
    "--config",
    default="config/settings.yaml",
    help="Path to settings YAML",
  )
  parser.add_argument(
    "--create-db",
    action="store_true",
    help="Create the PostgreSQL database if it does not exist",
  )
  parser.add_argument(
    "--init-views",
    action="store_true",
    help="Create dashboard SQL views for Excel Power Query",
  )
  parser.add_argument(
    "--init-db",
    action="store_true",
    help="Create star schema tables before loading",
  )
  parser.add_argument(
    "--input",
    type=Path,
    default=None,
    help="Single transformed CSV path. Default: load all files in data/transformed/",
  )
  return parser


def main() -> None:
  args = build_parser().parse_args()
  project_root = Path(__file__).resolve().parent
  load_dotenv(project_root / ".env")
  config = load_settings(project_root / args.config)

  transformed_dir = project_root / config["paths"]["transformed_dir"]
  staging_dir = project_root / config["paths"]["staging_dir"]
  schema_path = project_root / "load" / "schema.sql"
  views_path = project_root / "load" / "views.sql"

  if args.create_db:
    print("Ensuring PostgreSQL database exists...")
    ensure_database(config)
    print("Database ready.")

  if args.init_db:
    print(f"Initializing schema from {schema_path}")
    init_schema(config, schema_path)
    print("Schema ready.")

  if args.init_views:
    print(f"Initializing views from {views_path}")
    init_views(config, views_path)
    print("Views ready.")

  if args.init_views and not args.create_db and not args.init_db and not args.input:
    return

  if args.input:
    input_csv = args.input
    if not input_csv.exists():
      raise FileNotFoundError(f"Transformed CSV not found: {input_csv}")

    with connect(config) as conn:
      summary = load_transformed_csv(conn, input_csv, staging_dir)
    print("Load complete.")
    print(f"  Rows     : {summary['rows']}")
    print(f"  Inserted : {summary['inserted']}")
    print(f"  Updated  : {summary['updated']}")
    return

  results = load_all_transformed_files(config, transformed_dir, staging_dir)
  if not results:
    print(f"No transformed files found in {transformed_dir}")
    return

  print("Load complete.")
  for summary in results:
    print(
      f"  {summary['file']}: {summary['rows']} rows "
      f"({summary['inserted']} inserted, {summary['updated']} updated)"
    )


if __name__ == "__main__":
  main()
