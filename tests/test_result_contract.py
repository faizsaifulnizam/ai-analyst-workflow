import os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import duckdb
from src import validate, fingerprint, guardrails

class ResultContract(unittest.TestCase):
    def test_validator_classifies_unformattable_candidate_without_weakening_matcher(self):
        n,h=fingerprint.fingerprint([(1,)],2)
        with tempfile.TemporaryDirectory(dir=os.environ.get('AI_WORKFLOW_TEST_TMP')) as td:
            db=Path(td)/'db.duckdb'; duckdb.connect(str(db)).close()
            with patch.object(guardrails,'DB',db):
                for sql in ("SELECT CAST('NaN' AS DOUBLE)","SELECT CAST('Infinity' AS DOUBLE)",'SELECT [1,2]'):
                    result=validate.run_attempt(sql,{'rows':n,'sha256':h,'version':2})
                    self.assertFalse(result['ok'])
                    self.assertEqual(result['mismatch'],'result_contract_error')
                    self.assertTrue(result['note'])
