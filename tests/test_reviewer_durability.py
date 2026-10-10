import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import duckdb
from src import generate, fingerprint, guardrails

class FormattingDurability(unittest.TestCase):
    def test_completed_unformattable_sql_survives_outage_and_resumes_second_slot(self):
        for sql in ("SELECT CAST('NaN' AS DOUBLE)", "SELECT CAST('Infinity' AS DOUBLE)", "SELECT [1,2]"):
            with self.subTest(sql=sql), tempfile.TemporaryDirectory(dir=os.environ.get('AI_WORKFLOW_TEST_TMP')) as td:
                root=Path(td); db=root/'db.duckdb'; duckdb.connect(str(db)).close()
                gold=root/'gold.yaml'; gold.write_text('version: test\nquestions:\n- id: Q1\n  question: One\n  sql: SELECT 1\n')
                calls=[]
                def transport(url,payload=None,**kw):
                    if payload is None: return {'data':[{'id':'synthetic'}]}
                    calls.append(payload)
                    if len(calls)==2: raise OSError('synthetic outage')
                    return {'choices':[{'message':{'content':('```sql\n'+sql+'\n```') if len(calls)==1 else 'SELECT 1'}}]}
                with patch.object(guardrails,'DB',db),patch.object(fingerprint,'GOLDEN',gold),patch.object(generate,'http_json',transport),patch.object(generate.time,'sleep'),patch.dict(os.environ,{'GROQ_API_KEY':'synthetic'},clear=True),patch('sys.argv',['generate','--provider','groq','--out',str(root)]):
                    self.assertEqual(generate.main(),2)
                    journal=root/'candidates.jsonl'; before=journal.read_bytes()
                    saved=json.loads(before.splitlines()[-1])['attempts'][0]
                    self.assertEqual(saved['sql'],sql)
                    self.assertEqual(saved['response_text'],'```sql\n'+sql+'\n```')
                    self.assertEqual(saved['outcome'],'result_contract_error')
                    self.assertIsNone(saved['fingerprint'])
                    self.assertTrue(saved['note'])
                    self.assertEqual(generate.main(),0)
                    self.assertTrue(journal.read_bytes().startswith(before))
                    attempts=json.loads(journal.read_bytes().splitlines()[-1])['attempts']
                    self.assertEqual(attempts[0],saved)
                    self.assertEqual([a['n'] for a in attempts],[1,2])
                    self.assertEqual(len(calls),3)
                    self.assertNotIn(saved['note'],json.dumps(calls[-1]))
                    self.assertEqual(generate.main(),0)
                    self.assertEqual(len(calls),3)
