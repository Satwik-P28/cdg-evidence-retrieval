from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from speed_lab import run,METHODS


def test_identical_input_exact_decode_fixture():
    docs=[('The record','alpha beta alpha'),('Another','beta gamma'),('Last','alpha gamma beta'),('Delta','delta gamma')]
    r=run('fixture',docs)
    assert r['sampled_terms']>0
    assert r['sampled_posting_entries']>0
    assert r['wire_identical_barm_bytes']>0
    assert set(r['decode_warm_batch_ms_trials'])==set(METHODS)
    assert all(len(x)==7 for x in r['decode_warm_batch_ms_trials'].values())