"""Offline regressions for the observed SRPE defects. Run with unittest."""
import json
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from extract.pdf_parser import parse_register_pdf, ExtractionQualityError
from extract.ingestion_log import IngestionLog, IngestionRecord
from extract.downloader import register_local_pdf
from extract.pipeline import extract_local_pdf, extract_from_srpe_search
from transform.cleaners import parse_revised_price_hkd
from transform.payment_mapper import map_payment_category
from transform.pipeline import transform_transactions_df, transform_staging_csv, TransformQualityError

FIXTURE = Path(__file__).parent / 'fixtures' / 'srpe_sample.pdf'


class PipelineTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.development, cls.raw = parse_register_pdf(FIXTURE)
    cls.frame = pd.DataFrame([asdict(row) for row in cls.raw])

  def test_pdf_regular_open_tables_and_corrected_date(self):
    with TemporaryDirectory(dir=Path.cwd()) as tmp:
      report_path = Path(tmp) / 'quality.json'
      dev, raw = parse_register_pdf(FIXTURE, report_path=report_path)
      report = json.loads(report_path.read_text(encoding='utf-8'))
    self.assertEqual(len(raw), 15)
    self.assertEqual(dev.location_en, 'No. 18 Che Kung Miu Road')
    self.assertEqual(dev.location_tc, '車公廟路18號')
    self.assertEqual([p['source_page'] for p in report['pages'] if p['fallback']], [4, 5, 7])
    self.assertEqual(raw[-1].asp_date, '21/06/2021')
    self.assertEqual(report['pages'][-1]['struck_dates_excluded'], ['18/06/2021'])
    self.assertEqual(report['issues'], [])

  def test_unresolved_pdf_fails_before_publishing_staging(self):
    page = MagicMock()
    page.extract_text.return_value = '05/06/2021 11/06/2021 $9,726,000'
    page.extract_tables.return_value = []
    page.extract_words.return_value = []
    page.edges = []
    first = MagicMock()
    first.extract_text.return_value = 'Name of the Phase DEMO Phase No. (if any) 1'
    with TemporaryDirectory(dir=Path.cwd()) as tmp, patch('extract.pdf_parser.pdfplumber.open') as opened:
      opened.return_value.__enter__.return_value.pages = [first, page]
      folder = Path(tmp)
      log = IngestionLog(folder / 'ingestion.db')
      with self.assertRaises(ExtractionQualityError):
        extract_local_pdf(FIXTURE, staging_dir=folder, ingestion_log=log)
      self.assertFalse(list(folder.glob('*_transactions_raw.csv')))
      report = json.loads(next(folder.glob('*quality.json')).read_text(encoding='utf-8'))
      self.assertEqual(report['status'], 'failed')
      self.assertEqual(log.get_latest('UNRESOLVED', FIXTURE.name).status, 'failed')

  def test_remote_version_survives_parse(self):
    with TemporaryDirectory(dir=Path.cwd()) as tmp:
      log = IngestionLog(Path(tmp) / 'ingestion.db')
      digest = log.file_hash(FIXTURE)
      log.log(IngestionRecord(self.development.development_name_en, FIXTURE.name,
        'https://example.invalid/source.pdf', '2026-06-26', digest,
        'downloaded', None, log.now_iso()))
      register_local_pdf(FIXTURE, log, self.development.development_name_en)
      latest = log.get_latest(self.development.development_name_en, FIXTURE.name)
      self.assertEqual(latest.pdf_url, 'https://example.invalid/source.pdf')
      self.assertEqual(latest.server_last_modified, '2026-06-26')
      self.assertFalse(log.should_download(latest.development_name, FIXTURE.name, '2026-06-26', digest))
      self.assertTrue(log.should_download(latest.development_name, FIXTURE.name, '2026-06-27', digest))
      self.assertTrue(log.should_download(latest.development_name, FIXTURE.name, None, digest))
      self.assertTrue(log.should_download(latest.development_name, FIXTURE.name, '2026-06-26', 'changed'))

  def test_search_batch_reports_partial_failure(self):
    match = MagicMock(dev_id='7705', eng_phase_name='DEMO')
    with TemporaryDirectory(dir=Path.cwd()) as tmp, \
         patch('extract.pipeline.SrpeClient') as client, \
         patch('extract.pipeline.extract_from_srpe_development', side_effect=ExtractionQualityError('unresolved page')):
      client.return_value.__enter__.return_value.search_developments_by_name.return_value = [match]
      folder = Path(tmp)
      log = IngestionLog(folder / 'ingestion.db')
      with self.assertRaisesRegex(RuntimeError, '7705'):
        extract_from_srpe_search('DEMO', raw_pdf_dir=folder, staging_dir=folder,
          ingestion_log=log, settings={'extract': {'request_delay_seconds': 0}, 'srpe': {}})
      self.assertEqual(log.get_latest('DEMO', 'dev_7705.pdf').status, 'failed')

  def test_latest_price_and_payment_amendments(self):
    clean = transform_transactions_df(self.frame)
    self.assertEqual(len(clean), 15)
    self.assertEqual(clean[clean.source_page == 4].iloc[0].revised_price_hkd, 9319000)
    self.assertEqual(clean[clean.source_page == 4].iloc[0].payment_category, 'Cash Payment Plan')
    reversed_dates = ('On 02/02/2022, the price adjusted to $2,000 '
                      'On 01/01/2022, the price adjusted to $1,000')
    self.assertEqual(parse_revised_price_hkd(reversed_dates), 2000)
    payment = ('付款方法: 建築期付款 Terms of Payment '
      'On 02/02/2022, the terms of payment adjusted to 付款方法: 180天現金 Terms of Payment '
      'On 01/01/2022, the terms of payment adjusted to 付款方法: 建築期付款 Terms of Payment')
    self.assertEqual(map_payment_category(payment), 'Cash Payment Plan')
    with self.assertRaises(ValueError):
      map_payment_category('On 31/02/2022, the terms of payment adjusted to stage payment')
    with self.assertRaises(ValueError):
      parse_revised_price_hkd('adjusted to $1,000')
    with self.assertRaises(ValueError):
      parse_revised_price_hkd('On 01/01/2022, the price adjusted to $1,000; the price adjusted to $2,000')
    with self.assertRaises(ValueError):
      map_payment_category('On 01/01/2022, the terms of payment adjusted to stage payment; the terms of payment adjusted to cash payment')

  def test_bad_inputs_rejected_source_anomaly_preserved(self):
    for field, value in [('block_name', float('nan')), ('unit', None),
                         ('asp_date', '31/02/2026'), ('price_raw', '$-100')]:
      with self.subTest(field=field):
        sample = self.frame.iloc[:1].copy()
        sample.loc[sample.index[0], field] = value
        result = transform_transactions_df(sample)
        self.assertTrue(result.empty)
        self.assertTrue(any(i['severity'] == 'error' for i in result.attrs['quality_issues']))
    duplicated = transform_transactions_df(pd.concat([self.frame.iloc[:1]] * 2))
    self.assertIn('duplicate_natural_key', [i['reason'] for i in duplicated.attrs['quality_issues']])
    clean = transform_transactions_df(self.frame)
    anomaly = clean[(clean.floor == '10') & (clean.unit == 'D')].iloc[0]
    self.assertLess(anomaly.asp_date, anomaly.pasp_date)
    self.assertIn('asp_date_before_pasp_date', [i['reason'] for i in clean.attrs['quality_issues']])

  def test_failed_transform_reports_without_overwriting_clean(self):
    with TemporaryDirectory(dir=Path.cwd()) as tmp:
      staging, clean = Path(tmp) / 'raw.csv', Path(tmp) / 'clean.csv'
      self.frame.to_csv(staging, index=False)
      summary = transform_staging_csv(staging, clean)
      self.assertEqual(summary['output_rows'], 15)
      saved = clean.read_bytes()
      bad = self.frame.copy()
      bad.loc[0, 'asp_date'] = 'not a date'
      bad.to_csv(staging, index=False)
      with self.assertRaises(TransformQualityError):
        transform_staging_csv(staging, clean)
      self.assertEqual(clean.read_bytes(), saved)
      self.assertEqual(json.loads(clean.with_suffix('.quality.json').read_text(encoding='utf-8'))['status'], 'failed')


if __name__ == '__main__':
  unittest.main()
