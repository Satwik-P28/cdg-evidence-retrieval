#!/usr/bin/env python3
"""Retrieve the two question-only files used in Round 24, with Git-blob verification."""
from pathlib import Path
from urllib.request import urlopen
from title_probe import SOURCES, git_blob_sha
import argparse

REVISION = 'c9dc6c350accb3c07629f0465e57d38756a006b0'
BASE = f'https://raw.githubusercontent.com/surpradhan/rag-benchmark/{REVISION}/data/processed'

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output-dir',type=Path,default=Path('data/round-24-upstream'))
    args=p.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    for name, expected in SOURCES.items():
        url=f'{BASE}/{name}'
        with urlopen(url,timeout=45) as r:
            content=r.read()
        actual=git_blob_sha(content)
        if actual != expected:
            raise RuntimeError(f'{name}: expected {expected}, got {actual}; file NOT written')
        dest=args.output_dir/name
        dest.write_bytes(content)
        print(name,len(content),actual)
if __name__=='__main__':main()
