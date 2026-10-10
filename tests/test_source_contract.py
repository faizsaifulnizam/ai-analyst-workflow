import os
import unittest
from unittest.mock import patch
from src import download, build_db


class SourceParsing(unittest.TestCase):
    def test_full_build_rejects_nan_without_promoting_database(self):
        import os
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory(dir=os.environ.get('AI_WORKFLOW_TEST_TMP')) as td:
            root = Path(td)
            raw = root / 'data/raw/hdb-resale-prices-2017-onwards.csv'
            raw.parent.mkdir(parents=True)
            raw.write_text(download.EXPECTED_HEADER + '\n2017-01,TOWN,4 ROOM,1,ST,01 TO 03,90,Model,2000,80 years,NaN\n')
            out = root / 'data/processed/resale.duckdb'
            out.parent.mkdir(parents=True)
            out.write_bytes(b'previous DB')
            cwd = os.getcwd()
            try:
                with patch.object(build_db, 'ROOT', root), patch.object(build_db, 'RAW', raw), patch.object(build_db, 'OUT', out), \
                     patch.object(download, 'ROW_FLOOR', 1), patch.object(download, 'MONTH_FLOOR_LATE', '2017-01'):
                    with self.assertRaises(SystemExit):
                        build_db.main()
            finally:
                os.chdir(cwd)
            self.assertEqual(out.read_bytes(), b'previous DB')

    def test_logical_csv_arity_and_finite_numeric_and_lease_bounds(self):
        valid = '2017-01,TOWN,4 ROOM,1,ST,01 TO 03,90,Model,2000,80 years 01 months,500000\n'
        for bad in ['2017-01,TOWN\n', valid.replace(',90,', ',NaN,'),
                    valid.replace(',500000', ',inf'), valid.replace('01 months', '99 months')]:
            with patch.object(download, 'ROW_FLOOR', 1), patch.object(download, 'MONTH_FLOOR_LATE', '2017-01'):
                info, errors = download.validate((download.EXPECTED_HEADER + '\n' + bad).encode())
            self.assertTrue(errors, bad)
        with patch.object(download, 'ROW_FLOOR', 1), patch.object(download, 'MONTH_FLOOR_LATE', '2017-01'):
            info, errors = download.validate((download.EXPECTED_HEADER + '\n' + valid.replace('ST,', '"ST, ONE",')).encode())
        self.assertFalse(errors)
        self.assertEqual(info['rows'], 1)


if __name__ == '__main__':
    unittest.main()
