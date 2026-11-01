"""Opt-in integration test; creates and drops only its own UUID test database."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import uuid

from dotenv import load_dotenv
import pandas as pd
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import yaml

from extract.pdf_parser import parse_register_pdf, write_staging_csv
from load.db import DatabaseConfig
from load.loader import load_transformed_csv
from transform.pipeline import transform_staging_csv

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.getenv('SRPE_RUN_DB_TESTS') == '1', 'set SRPE_RUN_DB_TESTS=1 to create an isolated test database')
class PostgresTests(unittest.TestCase):
  def test_load_reload_amendments_and_all_queries(self):
    load_dotenv(ROOT / '.env')
    settings = yaml.safe_load((ROOT / 'config/settings.yaml').read_text(encoding='utf-8'))
    base = DatabaseConfig.from_settings(settings).conninfo()
    database_name = 'srpe_test_' + uuid.uuid4().hex
    with psycopg.connect(make_conninfo(base, dbname='postgres'), autocommit=True) as admin:
      admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database_name)))
      try:
        with TemporaryDirectory(dir=ROOT) as temporary:
          folder = Path(temporary)
          full_csv = os.getenv('SRPE_TEST_FULL_CSV')
          if full_csv:
            clean = Path(full_csv).resolve()
            staging = ROOT / 'data/staging'
          else:
            dev, rows = parse_register_pdf(ROOT / 'tests/fixtures/srpe_sample.pdf')
            _, raw_csv = write_staging_csv(dev, rows, folder)
            clean, staging = folder / 'sample_transactions_clean.csv', folder
            transform_staging_csv(raw_csv, clean)
          frame = pd.read_csv(clean, dtype=str, keep_default_na=False)
          with psycopg.connect(make_conninfo(base, dbname=database_name)) as conn:
            conn.execute((ROOT / 'load/schema.sql').read_text(encoding='utf-8'))
            conn.execute((ROOT / 'load/views.sql').read_text(encoding='utf-8'))
            conn.commit()
            first = load_transformed_csv(conn, clean, staging)
            self.assertEqual(first['inserted'], len(frame))
            second = load_transformed_csv(conn, clean, staging)
            self.assertEqual(second['inserted'], 0)
            self.assertEqual(second['updated'], len(frame))
            self.assertEqual(conn.execute('SELECT COUNT(*), COUNT(DISTINCT natural_key) FROM fact_sales').fetchone(), (len(frame), len(frame)))
            actual = conn.execute('SELECT natural_key, price_hkd, revised_price_hkd, transaction_status FROM fact_sales ORDER BY natural_key').fetchall()
            expected = [(r.natural_key, int(r.price_hkd), int(r.revised_price_hkd) if r.revised_price_hkd else None, r.transaction_status)
                        for r in frame.sort_values('natural_key').itertuples()]
            self.assertEqual(actual, expected)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM vw_sales_detail').fetchone()[0], len(frame))
            actual_payments = conn.execute('SELECT natural_key, payment_category FROM vw_sales_detail ORDER BY natural_key').fetchall()
            self.assertEqual(actual_payments, list(frame.sort_values('natural_key')[['natural_key','payment_category']].itertuples(index=False, name=None)))
            expected_signed_mean = round(frame.loc[frame.transaction_status == 'asp_signed'].apply(
              lambda r: int(r.revised_price_hkd or r.price_hkd), axis=1).mean())
            self.assertEqual(int(conn.execute("SELECT ROUND(AVG(final_price_hkd)) FROM vw_sales_detail WHERE transaction_status='asp_signed'").fetchone()[0]), expected_signed_mean)
            month_rows = conn.execute('SELECT pasp_month, transaction_count, termination_rate_pct FROM vw_monthly_sales ORDER BY pasp_month').fetchall()
            self.assertEqual(sum(r[1] for r in month_rows), len(frame))
            self.assertTrue(any(r[1] == 0 and r[2] is None for r in month_rows))
            statements = [q for q in (ROOT / 'load/sample_queries.sql').read_text(encoding='utf-8').split(';') if q.strip()]
            self.assertEqual(len(statements), 6)
            for query in statements:
              conn.execute(query).fetchall()
            changed = frame.iloc[:1].copy()
            key = changed.iloc[0].natural_key
            sale_key = conn.execute('SELECT sale_key FROM fact_sales WHERE natural_key=%s', (key,)).fetchone()[0]
            changed.loc[changed.index[0], 'revised_price_hkd'] = '9000001'
            changed.loc[changed.index[0], 'termination_date'] = '2026-06-27'
            changed.loc[changed.index[0], 'transaction_status'] = 'terminated'
            amended_csv = folder / 'amended_transactions_clean.csv'
            changed.to_csv(amended_csv, index=False)
            amended = load_transformed_csv(conn, amended_csv, staging)
            self.assertEqual(amended['updated'], 1)
            self.assertEqual(conn.execute('SELECT sale_key, revised_price_hkd, transaction_status FROM fact_sales WHERE natural_key=%s', (key,)).fetchone(), (sale_key, 9000001, 'terminated'))
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM fact_sales').fetchone()[0], len(frame))
            # Restore original test contents and verify a failed report blocks load.
            load_transformed_csv(conn, clean, staging)
            amended_csv.with_suffix('.quality.json').write_text('{"status":"failed"}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'quality report'):
              load_transformed_csv(conn, amended_csv, staging)
      finally:
        # This name was generated and created above, never a user database.
        assert database_name.startswith('srpe_test_') and len(database_name) == 42
        admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(database_name)))


if __name__ == '__main__':
  unittest.main()
