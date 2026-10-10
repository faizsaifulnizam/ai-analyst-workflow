import json
import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import patch
import duckdb
from src import generate, fingerprint, guardrails


class Durability(unittest.TestCase):
    def test_generation_dates_are_evaluated_at_receipt_clock(self):
        from datetime import datetime, timezone
        class Clock:
            @staticmethod
            def now(tz=None): return datetime(2020,1,2,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory(dir=os.environ.get('AI_WORKFLOW_TEST_TMP')) as td:
            root=Path(td); db=root/'db.duckdb'; duckdb.connect(str(db)).close()
            gold=root/'gold.yaml'
            gold.write_text("version: test\nquestions:\n- id: Q1\n  question: Today\n  sql: SELECT DATE '2020-01-02'\n")
            calls=[]
            def transport(url,payload=None,**kw):
                if payload is None:return {'data':[{'id':'synthetic'}]}
                calls.append(payload)
                return {'choices':[{'message':{'content':'SELECT CURRENT_DATE'}}]}
            with patch.object(guardrails,'DB',db),patch.object(fingerprint,'GOLDEN',gold),patch.object(generate,'datetime',Clock), \
                 patch.object(generate,'http_json',transport),patch.object(generate.time,'sleep'), \
                 patch.dict(generate.os.environ,{'GROQ_API_KEY':'synthetic-key'},clear=True), \
                 patch('sys.argv',['generate','--provider','groq','--out',str(root)]):
                self.assertEqual(generate.main(),0)
            self.assertEqual(len(calls),1)

    def test_shape_collision_requires_retry_in_new_generation(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('AI_WORKFLOW_TEST_TMP')) as td:
            root=Path(td); db=root/'db.duckdb'; duckdb.connect(str(db)).close()
            n,h=fingerprint.fingerprint([('A','B')])
            gold=root/'gold.yaml'
            gold.write_text(f"version: test\nquestions:\n- id: Q1\n  question: Two columns\n  sql: SELECT 'A', 'B'\n  fingerprint: {{rows: {n}, sha256: {h}}}\n")
            calls=[]
            def transport(url,payload=None,**kw):
                if payload is None: return {'data':[{'id':'synthetic'}]}
                calls.append(payload)
                return {'choices':[{'message':{'content':"SELECT 'A' || chr(31) || 'B'" if len(calls)==1 else "SELECT 'A', 'B'"}}]}
            with patch.object(guardrails,'DB',db),patch.object(fingerprint,'GOLDEN',gold),patch.object(generate,'http_json',transport), \
                 patch.object(generate.time,'sleep'),patch.dict(generate.os.environ,{'GROQ_API_KEY':'synthetic-key'},clear=True), \
                 patch('sys.argv',['generate','--provider','groq','--out',str(root)]):
                self.assertEqual(generate.main(),0)
            self.assertEqual(len(calls),2)

    def test_second_call_failure_preserves_first_attempt_and_resume(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('AI_WORKFLOW_TEST_TMP')) as td:
            root = Path(td)
            db = root / 'test.duckdb'
            duckdb.connect(str(db)).close()
            n, h = fingerprint.fingerprint([(1,)])
            gold = root / 'gold.yaml'
            gold.write_text(f'version: test\nquestions:\n- id: Q1\n  question: One\n  sql: SELECT 1\n  fingerprint: {{rows: {n}, sha256: {h}}}\n')
            calls = []
            def transport(url, payload=None, **kw):
                if payload is None:
                    return {'data': [{'id': 'synthetic'}]}
                calls.append(payload)
                if len(calls) == 2:
                    raise OSError('synthetic transport fault')
                return {'choices': [{'message': {'content': 'SELECT 2' if len(calls) == 1 else 'SELECT 1'}}]}
            with patch.object(guardrails, 'DB', db), patch.object(fingerprint, 'GOLDEN', gold), \
                 patch.object(generate, 'http_json', transport), patch.object(generate.time, 'sleep'), \
                 patch.dict(generate.os.environ, {'GROQ_API_KEY': 'synthetic-key'}, clear=True), \
                 patch('sys.argv', ['generate', '--provider', 'groq', '--out', str(root)]):
                self.assertEqual(generate.main(), 2)
                records = [json.loads(x) for x in (root / 'candidates.jsonl').read_text().splitlines()]
                self.assertEqual(records[-1].get('attempts', []), [{'n': 1, 'sql': 'SELECT 2', 'outcome': 'ok', 'note': '', 'fingerprint': list(fingerprint.fingerprint([(2,)], version=2))}])
                self.assertEqual(generate.main(), 0)
                self.assertEqual(len(calls), 3)
                with patch('sys.argv', ['generate', '--provider', 'groq', '--model', 'different', '--out', str(root)]):
                    self.assertEqual(generate.main(), 2)
                self.assertEqual(len(calls), 3)
                gold.write_text(gold.read_text().replace('question: One', 'question: Changed'))
                self.assertEqual(generate.main(), 2)
                self.assertEqual(len(calls), 3)


if __name__ == '__main__':
    unittest.main()
