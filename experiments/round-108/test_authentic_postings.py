from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from authentic_postings import run, sample_postings, compare_lists
from codec_controls import CODECS
import sqlite3


def test_small_actual_fts5_vocabulary_and_group_accounting():
    docs=[('Alpha','alpha beta alpha'),('Beta','beta gamma'),('X','alpha gamma'),('Z','alpha delta gamma'),('Z','beta')]
    result=run('fixture',docs)
    assert result['num_documents']==5
    assert result['sampled_terms']>0
    assert result['sampled_posting_entries']>0
    assert all(result['sizes_bytes'][c]>0 for c in CODECS)
    assert 'not replaced' in result['limitations'][0]


def test_stratified_sampling_deterministic_and_source_independent():
    docs=[(f'Doc {i}', 'common ubiquitous '+('rare' if i%9==0 else 'ordinary')) for i in range(100)]
    a=run('fixture',docs);b=run('fixture',docs)
    assert a['sizes_bytes']==b['sizes_bytes']
    assert {k:v['selected_term_sha256'] for k,v in a['by_df'].items()}=={k:v['selected_term_sha256'] for k,v in b['by_df'].items()}


def test_small_df_band_never_hidden():
    docs=[('',f'unique{i} common') for i in range(8)]
    r=run('fixture',docs)
    assert r['by_df']['df1']['sampled_terms']>=8
    assert r['by_df']['df4_31']['sampled_terms']>=1