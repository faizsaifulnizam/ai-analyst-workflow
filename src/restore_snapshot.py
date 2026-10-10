"""Restore the licensed historical source; live refresh is src/download.py."""
import argparse
import gzip
import hashlib
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SHA='9835dfe6cd92a46a1302fabf3a692bf893ee5b86ec95638d10dfce61dbfbdb9a'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',default=str(ROOT/'data/raw/hdb-resale-prices-2017-onwards.csv'))
    args=parser.parse_args()
    data=gzip.decompress((ROOT/'data/snapshots/hdb-2026-10-04.csv.gz').read_bytes())
    if hashlib.sha256(data).hexdigest()!=SHA:
        raise SystemExit('snapshot integrity failure')
    target=Path(args.out)
    target.parent.mkdir(parents=True,exist_ok=True)
    part=target.with_name(target.name+'.part')
    try:
        part.write_bytes(data)
        os.replace(part,target)
    finally:
        part.unlink(missing_ok=True)
    print(f'restored {len(data)} bytes; SHA-256 {SHA}')


if __name__=='__main__': main()
