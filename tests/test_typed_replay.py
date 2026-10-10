import json
import subprocess
import sys
import tempfile
import os
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


class TypedReplay(unittest.TestCase):
    def test_validator_labels_v2_candidates_without_relabelling_historical(self):
        from src import validate
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(dir=os.environ.get('AI_WORKFLOW_TEST_TMP')) as td:
            root=Path(td); cand=root/'candidates.jsonl'
            records=[json.loads(x) for x in (ROOT/'outputs/candidates.jsonl').read_text().splitlines()]
            records[0]['meta']['serializer_version']=2
            cand.write_text('\n'.join(json.dumps(x) for x in records)+'\n')
            with patch('sys.argv',['validate','--candidates',str(cand)]):
                self.assertEqual(validate.main(),0)
            self.assertEqual(json.loads((root/'summary.json').read_text())['receipt']['serializer_version'],2)

    def test_all_32_references_and_candidates_have_separate_versioned_receipt(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('AI_WORKFLOW_TEST_TMP')) as td:
            path=Path(td)/'typed.json'
            result=subprocess.run([sys.executable, str(ROOT/'src/replay_typed.py'), '--out', str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt=json.loads(path.read_text())
            self.assertEqual(receipt['serializer_version'], 2)
            self.assertEqual(len(receipt['questions']), 32)
            self.assertEqual(sum(q['status']=='pass_first_try' for q in receipt['questions']), 27)
            self.assertEqual(receipt['q15_mismatch_months'], ['2022-04','2022-09','2023-01','2023-03','2023-05','2023-09'])


if __name__=='__main__': unittest.main()
