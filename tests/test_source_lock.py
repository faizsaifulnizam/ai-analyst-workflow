import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from src import validate


class SourceLock(unittest.TestCase):
    def test_database_provenance_mismatch_fails_with_matching_pins(self):
        import shutil
        import duckdb
        from src import guardrails
        with tempfile.TemporaryDirectory(dir=os.environ.get('AI_WORKFLOW_TEST_TMP')) as td:
            root=Path(td); db=root/'db.duckdb'
            shutil.copyfile(guardrails.DB,db)
            con=duckdb.connect(str(db))
            con.execute("CREATE OR REPLACE TABLE source_receipt AS SELECT 'different-source' AS sha256")
            con.close()
            out=root/'out'
            with patch.object(guardrails,'DB',db),patch('sys.argv',['validate','--outdir',str(out)]):
                self.assertEqual(validate.main(),1)
            self.assertFalse(out.exists())

    def test_source_append_fails_before_publication_even_when_gold_unchanged(self):
        original = validate.ROOT
        with tempfile.TemporaryDirectory(dir=os.environ.get('AI_WORKFLOW_TEST_TMP')) as td:
            root = Path(td)
            raw = root / 'data/raw/hdb-resale-prices-2017-onwards.csv'
            raw.parent.mkdir(parents=True)
            raw.write_bytes((original / 'data/raw/hdb-resale-prices-2017-onwards.csv').read_bytes() + b'2026-10,TAMPINES,4 ROOM,999,SYNTHETIC ST,01 TO 03,90,Model A,2000,80 years,500000\n')
            out = root / 'out'
            with patch.object(validate, 'ROOT', root), patch('sys.argv', ['validate', '--candidates', str(original / 'outputs/candidates.jsonl'), '--outdir', str(out)]):
                self.assertEqual(validate.main(), 1)
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
