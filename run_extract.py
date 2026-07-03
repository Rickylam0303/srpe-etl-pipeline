"""CLI entrypoint for the Extract layer."""

from __future__ import annotations

import argparse
from pathlib import Path

from extract.ingestion_log import IngestionLog
from extract.pipeline import (
  extract_from_srpe_development,
  extract_from_srpe_search,
  extract_local_pdf,
  load_settings,
)


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description="SRPE Extract layer")
  parser.add_argument(
    "--config",
    default="config/settings.yaml",
    help="Path to settings YAML",
  )

  subparsers = parser.add_subparsers(dest="command", required=True)

  local = subparsers.add_parser("local", help="Parse a local Register of Transactions PDF")
  local.add_argument("--pdf", required=True, type=Path, help="Path to a local RT PDF")

  srpe = subparsers.add_parser("srpe", help="Download from SRPE, then parse to staging CSV")
  srpe_group = srpe.add_mutually_exclusive_group(required=True)
  srpe_group.add_argument("--search", help="Search SRPE by development name")
  srpe_group.add_argument("--dev-id", help="Download one development by SRPE devId")
  srpe.add_argument(
    "--limit",
    type=int,
    default=None,
    help="When using --search, limit how many matching developments to process",
  )

  return parser


def main() -> None:
  args = build_parser().parse_args()
  project_root = Path(__file__).resolve().parent
  config = load_settings(project_root / args.config)

  staging_dir = project_root / config["paths"]["staging_dir"]
  raw_pdf_dir = project_root / config["paths"]["raw_pdf_dir"]
  log_db = project_root / config["paths"]["ingestion_log_db"]
  ingestion_log = IngestionLog(log_db)

  if args.command == "local":
    pdf_path = args.pdf
    if not pdf_path.exists():
      raise FileNotFoundError(f"PDF not found: {pdf_path}")

    print(f"[1/2] Parsing local PDF: {pdf_path.name}")
    result = extract_local_pdf(
      pdf_path,
      staging_dir=staging_dir,
      ingestion_log=ingestion_log,
    )
    print(f"      Development : {result.development_name}")
    print(f"      Transactions: {result.transaction_count}")
    print(f"[2/2] Staging CSV written:")
    print(f"      {result.development_csv}")
    print(f"      {result.transactions_csv}")
    print(f"      Log DB: {log_db}")
    print("Done.")
    return

  if args.command == "srpe":
    if args.dev_id:
      print(f"[SRPE] Download + extract devId={args.dev_id}")
      result = extract_from_srpe_development(
        args.dev_id,
        raw_pdf_dir=raw_pdf_dir,
        staging_dir=staging_dir,
        ingestion_log=ingestion_log,
        settings=config,
      )
      _print_result(result, log_db)
      return

    print(f"[SRPE] Search + extract name={args.search!r}")
    results = extract_from_srpe_search(
      args.search,
      raw_pdf_dir=raw_pdf_dir,
      staging_dir=staging_dir,
      ingestion_log=ingestion_log,
      settings=config,
      limit=args.limit,
    )
    if not results:
      print("No developments processed.")
      return
    for result in results:
      _print_result(result, log_db)
    print(f"Processed {len(results)} development(s).")
    return


def _print_result(result, log_db: Path) -> None:
  print(f"  Development : {result.development_name}")
  print(f"  PDF         : {result.pdf_path}")
  print(f"  Transactions: {result.transaction_count}")
  print(f"  Staging     : {result.transactions_csv}")
  print(f"  Log DB      : {log_db}")


if __name__ == "__main__":
  main()
