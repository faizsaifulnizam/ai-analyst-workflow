import hashlib
import subprocess
import sys
import tempfile
import os
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


class Snapshot(unittest.TestCase):
    def test_archive_restores_exact_historical_bytes(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('AI_WORKFLOW_TEST_TMP')) as td:
            out=Path(td)/'raw.csv'
            result=subprocess.run([sys.executable, str(ROOT/'src/restore_snapshot.py'), '--out', str(out)], capture_output=True, text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(hashlib.sha256(out.read_bytes()).hexdigest(),'9835dfe6cd92a46a1302fabf3a692bf893ee5b86ec95638d10dfce61dbfbdb9a')


if __name__=='__main__': unittest.main()
