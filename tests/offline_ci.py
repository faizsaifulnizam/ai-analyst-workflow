"""Frozen offline acceptance lane. Run after installing requirements.txt."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def run_suite(suite):
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.testsRun or result.skipped or not result.wasSuccessful():
        raise RuntimeError('offline suite must be nonempty, successful, and have zero skips')
    return result.testsRun

def main():
    # Never invoke generation/download; dependencies are installed separately.
    for key in ('GOOGLE_API_KEY','GROQ_API_KEY'):
        os.environ.pop(key,None)
    paths=['eval/golden_set.yaml','outputs/candidates.jsonl','outputs/results.csv','outputs/summary.json']
    original={p:subprocess.check_output(['git','show','HEAD:'+p],cwd=ROOT) for p in paths}
    def stage(*args):
        subprocess.run([sys.executable,*args],cwd=ROOT,check=True)
    with tempfile.TemporaryDirectory(dir=os.environ.get('AI_WORKFLOW_TEST_TMP')) as td:
        receipt=Path(td)/'typed.json'
        stage('src/restore_snapshot.py')
        stage('src/build_db.py')
        stage('src/validate.py')
        stage('src/fingerprint.py')
        stage('src/guardrails.py')
        count=run_suite(unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_*.py'))
        stage('tests/test_validate_outdir.py')
        stage('src/replay_typed.py','--out',str(receipt))
        data=json.loads(receipt.read_text()); questions=data['questions']
        assert len(questions)==32 and sum(len(q['attempts']) for q in questions)==37
        assert all(a['match']==a['direct_rows_equal'] for q in questions for a in q['attempts'])
        assert [sum(q['status']==s for q in questions) for s in ('pass_first_try','pass_after_retry','fail')]==[27,0,5]
        totals=json.loads((ROOT/'outputs/summary.json').read_text())['totals']
        assert [totals[k] for k in ('pass_first_try','pass_after_retry','fail')]==[27,0,5]
        # Same-environment render reproducibility, complete reports/site mirrors.
        figures=[*ROOT.glob('reports/figures/*.png'),*ROOT.glob('docs/img/f*.png')]
        assert len(figures)==8
        stage('src/figures.py'); first={p:p.read_bytes() for p in figures}
        stage('src/figures.py'); assert all(p.read_bytes()==b for p,b in first.items())
        for p in ROOT.glob('reports/figures/*.png'):
            assert p.read_bytes()==(ROOT/'docs/img'/p.name).read_bytes()
    for p,b in original.items():
        assert (ROOT/p).read_bytes()==b, 'historical receipt changed: '+p
    print(f'Offline acceptance: {count} tests, zero skips; 32 references/37 attempts; 27/0/5; original receipt bytes preserved; complete mirrors')
    return 0

if __name__=='__main__': sys.exit(main())
