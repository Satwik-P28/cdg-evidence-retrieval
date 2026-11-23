import sys
from pathlib import Path
import sqlite3
import tempfile
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from full_bm25_store import (
    make_fts,collect_postings,choose_codec,ids_to_gaps,gaps_to_ids,pack_postings,
    unpack_postings,build_store,fetch_term,rank_query,query_plan,verify_queries,run,CODECS,
)

DOCS=[
    ('alpha beta','alpha alpha gamma'),
    ('gamma','alpha beta'),
    ('beta','beta delta'),
    ('alpha delta','alpha beta beta'),
    ('long title','nothing pertinent here'),
    ('alpha','alpha alpha beta gamma'),
    ('delta gamma','gamma beta'),
    ('beta gamma','alpha delta beta'),
]

@pytest.mark.parametrize('family',CODECS)
def test_full_copy_and_scores(family):
    with tempfile.TemporaryDirectory() as d:
        with make_fts(Path(d)/'fts.sqlite',DOCS) as fts:
            by_term,doclen=collect_postings(fts,len(DOCS))
            assert sum(doclen)==sum(sum(t) for i,t in by_term.values())
            path=Path(d)/f'{family}.sqlite'
            result=build_store(path,by_term,doclen,family)
            assert result['sqlite_bytes']>=result['payload_bytes']
            with sqlite3.connect(path) as db:
                for term,(ids,tf) in by_term.items():assert fetch_term(db,term)==(ids,tf)
                assert fetch_term(db,'doesnotexist')==([],[])
                q=[('alpha',),('beta',),('alpha','beta'),('alpha','gamma'),('alpha','delta')]
                report=verify_queries(db,fts,q,len(DOCS),sum(doclen)/len(DOCS))
                assert report['queries']==5
                assert report['scores_match_abs_1e_12']

@pytest.mark.parametrize('family',CODECS)
def test_wire_corruption_guards(family):
    ids=[2,3,10,11,19]
    freq=[3,1,1,4,2]
    raw=pack_postings(ids,freq,family)
    assert unpack_postings(raw,len(ids))==(ids,freq)
    for bad in (b'',raw[:4],bytes([255])+raw[1:],raw[:5]+b'',raw[:-1]):
        with pytest.raises((ValueError,IndexError)):unpack_postings(bad,len(ids))
    with pytest.raises(ValueError):unpack_postings(raw,len(ids)+1)

@pytest.mark.parametrize('family',CODECS)
def test_empty_term_or_bad_freq(family):
    with pytest.raises(ValueError):pack_postings([],[],family)
    with pytest.raises(ValueError):pack_postings([2,4],[0,1],family)
    with pytest.raises(ValueError):pack_postings([2,2],[1,1],family)


def test_original_full_vocabulary_fixture_run():
    result=run('fixture',docs=DOCS)
    assert result['documents']==len(DOCS)
    assert result['full_token_vocabulary_terms']>4
    assert result['queried_terms_and_pairs']>0
    assert all(v['bm25_verification']['scores_match_abs_1e_12'] for v in result['codecs'].values())
    assert result['codecs']['barm_r']['number_of_terms']==result['full_token_vocabulary_terms']


def test_selectors_short_lists_and_boundaries():
    assert choose_codec([4,2,3],'hybrid_df4')=='varint'
    assert choose_codec([4,2,3,4],'hybrid_df4')=='barm_r'
    assert ids_to_gaps([1,3,6,9])==[1,2,3,3]
    assert gaps_to_ids([1,2,3,3])==[1,3,6,9]
    for ids in ([0],[-1],[2,2],[4,3]):
        with pytest.raises(ValueError):ids_to_gaps(ids)

@pytest.mark.parametrize('seed',range(10))
def test_randomized_bm25_exact_frequency_controls(seed):
    import random
    rng=random.Random(11000+seed)
    vocabulary=['alpha','beta','gamma','delta','xi','omega','κ','research','archive','retrieval','test','time']
    docs=[]
    for k in range(24):
        words=[rng.choice(vocabulary) for _ in range(rng.randint(1,28))]
        docs.append((' '.join(words[:3]),' '.join(words[3:])))
    with tempfile.TemporaryDirectory() as d:
        with make_fts(Path(d)/'fts.sqlite',docs) as fts:
            by_term,dl=collect_postings(fts,len(docs))
            path=Path(d)/'index.sqlite'
            build_store(path,by_term,dl,'hybrid_df4')
            with sqlite3.connect(path) as db:
                q=[(t,) for t in by_term]
                q += [(a,b) for a,b in [('alpha','beta'),('gamma','xi'),('omega','research')]
                      if a in by_term and b in by_term]
                ver=verify_queries(db,fts,q,len(docs),sum(dl)/len(docs))
                assert ver['queries']==len(q)
                assert ver['scores_match_abs_1e_12']