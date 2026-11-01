"""CLI entrypoint for the Transform layer."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from transform.pipeline import transform_all_staging_files, transform_staging_csv


def load_settings(config_path: Path) -> dict:
  with config_path.open(encoding="utf-8") as handle:
    return yaml.safe_load(handle)


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description="SRPE Transform layer")
  parser.add_argument(
    "--config",
    default="config/settings.yaml",
    help="Path to settings YAML",
  )
  parser.add_argument(
    "--input",
    type=Path,
    default=None,
    help="Single staging CSV path. Default: process all files in data/staging/",
  )
  return parser


def main() -> None:
  args = build_parser().parse_args()
  project_root = Path(__file__).resolve().parent
  config = load_settings(project_root / args.config)

  staging_dir = project_root / config["paths"]["staging_dir"]
  transformed_dir = project_root / config["paths"]["transformed_dir"]

  if args.input:
    input_csv = args.input
    if not input_csv.exists():
      raise FileNotFoundError(f"Staging CSV not found: {input_csv}")

    stem = input_csv.name.removesuffix('_transactions_raw.csv') if input_csv.name.endswith('_transactions_raw.csv') else input_csv.stem
    output_csv = transformed_dir / f"{stem}_transactions_clean.csv"
    summary = transform_staging_csv(input_csv, output_csv)
    print("Transform complete.")
    print(f"  Input rows : {summary['input_rows']}")
    print(f"  Output rows: {summary['output_rows']}")
    print(f"  Dropped rows: {summary['dropped_rows']}")
    print(f"  Unmapped payment rows: {summary['unmapped_payment_rows']}")
    print(f"  Output CSV : {summary['output_csv']}")
    print(f"  Quality report: {summary['quality_report']} ({summary['warning_count']} warnings)")
    return

  results = transform_all_staging_files(staging_dir, transformed_dir)
  if not results:
    print(f"No staging files found in {staging_dir}")
    return

  print("Transform complete.")
  for summary in results:
    print(f"  {summary['development']}: {summary['output_rows']} rows -> {summary['output_csv']}")
    print(f"    Quality report: {summary['quality_report']} ({summary['warning_count']} warnings)")
    if summary["unmapped_payment_rows"]:
      print(f"    Unmapped payment rows: {summary['unmapped_payment_rows']}")


if __name__ == "__main__":
  main()
