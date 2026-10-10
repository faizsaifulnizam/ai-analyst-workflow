"""New typed replay evidence, never a replacement for historical v1 receipts."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.fingerprint import fingerprint, load_golden
from src.guardrails import execute_sql
from src.publication import publish

from src.validate import SOURCE_SHA, frozen_source_valid


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args=parser.parse_args()
    out=Path(args.out).resolve()
    if out.parent == (ROOT/'outputs').resolve() or out.suffix != '.json':
        raise SystemExit('use a separate JSON receipt path, not historical outputs/')
    if not frozen_source_valid():
        return 1
    candidates={}; meta={}
    for line in (ROOT/'outputs/candidates.jsonl').read_text().splitlines():
        record=json.loads(line)
        if 'meta' in record: meta=record['meta']
        else: candidates[record['id']]=record
    golden=load_golden(); questions=[]; q15=[]
    for q in golden['questions']:
        reference=execute_sql(q['sql'], as_of=meta['run_date'])
        if reference['outcome'] != 'ok': raise RuntimeError(reference)
        want=fingerprint(reference['rows'], version=2)
        attempts=[]
        for attempt in candidates[q['id']]['attempts']:
            result=execute_sql(attempt['sql'], as_of=meta['run_date'])
            got=fingerprint(result['rows'], version=2) if result['outcome']=='ok' else None
            attempts.append({'n':attempt['n'], 'outcome':result['outcome'], 'fingerprint':got, 'match':got==want,
                             'direct_rows_equal':result.get('rows')==reference['rows']})
            if q['id']=='Q15' and attempt['n']==1:
                q15=[str(a[0])[:7] for a,b in zip(reference['rows'],result['rows']) if a!=b]
        status='pass_first_try' if attempts[0]['match'] else ('pass_after_retry' if any(a['match'] for a in attempts[1:]) else 'fail')
        questions.append({'id':q['id'], 'reference_fingerprint':want, 'attempts':attempts, 'status':status})
    receipt={'serializer_version':2, 'numeric_contract':'2dp Decimal without float conversion; typed JSON framing; ordered rows',
             'source_sha256':SOURCE_SHA, 'as_of':meta['run_date'], 'golden_set_version':golden['version'],
             'historical_receipts_changed':False, 'questions':questions, 'q15_mismatch_months':q15}
    out.parent.mkdir(parents=True, exist_ok=True)
    publish({out:(json.dumps(receipt, indent=2)+'\n').encode()})
    print(f'{len(questions)} references and all candidate attempts replayed; wrote {out}')
    return 0


if __name__=='__main__': sys.exit(main())
