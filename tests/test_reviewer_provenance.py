import os, shutil, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import duckdb
from src import guardrails, replay_typed, validate

class Provenance(unittest.TestCase):
    def test_typed_main_rejects_bad_database_before_execution_and_preserves_receipt(self):
        for mode in ('contradictory', 'missing'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(dir=os.environ.get('AI_WORKFLOW_TEST_TMP')) as td:
                root=Path(td); db=root/'db.duckdb'; shutil.copyfile(guardrails.DB,db)
                con=duckdb.connect(str(db))
                con.execute("UPDATE source_receipt SET sha256='contradictory'" if mode=='contradictory' else 'DROP TABLE source_receipt'); con.close()
                out=root/'typed.json'; out.write_bytes(b'previous receipt')
                with patch.object(guardrails,'DB',db), patch.object(replay_typed,'execute_sql',side_effect=AssertionError('reference executed before gate')), patch('sys.argv',['replay_typed','--out',str(out)]):
                    self.assertEqual(replay_typed.main(),1)
                self.assertEqual(out.read_bytes(),b'previous receipt')
                with patch.object(guardrails,'DB',db),patch('sys.argv',['validate','--outdir',str(root/'validation')]):
                    self.assertEqual(validate.main(),1)
                self.assertFalse((root/'validation').exists())
