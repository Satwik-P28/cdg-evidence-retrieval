from __future__ import annotations
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from positional_store import (
 ATOMIC,FAMILIES,make_fts,collect_positions,to_positive_gaps,from_positive_gaps,
 positions_to_gaps,gaps_to_positions,pack_term,unpack_term,fetch,phrase_match,bm25_query,
 build_store,run,plan,verify,
)

DOCS=[
 (f'Paper {i} alpha beta',
  ('alpha beta gamma beta alpha delta '*(i%5+1)) +
  (('novel scientific fact ' if i%3==0 else 'another measured outcome ')*4)+
  (('alpha beta' if i%4==0 else 'beta alpha')))
 for i in range(1,38)
]

@pytest.mark.parametrize('family',FAMILIES)
def test_encode_decode_every_family(family):
    ids=[1,3,9,100]
    groups=[[0,2,5],[0],[8,19,21],[1,3,4,44]]
    row=pack_term(ids,groups,family)
    out=unpack_term(len(ids),*row)
    assert out==(ids,list(map(len,groups)),groups)
    assert unpack_term(len(ids),*row[:4])==(ids,list(map(len,groups)),None)

@pytest.mark.parametrize('groups',[[[0],[0,3]],[[2,5,9],[4,5]],[[0]],[[10,11,50]]])
def test_position_gaps(groups):
    gaps=positions_to_gaps(groups)
    assert min(gaps)>0
    assert gaps_to_positions(gaps,list(map(len,groups)))==groups

@pytest.mark.parametrize('ids',[[1],[1,2,3],[5,10,100]])
def test_doc_gaps(ids):
    assert from_positive_gaps(to_positive_gaps(ids))==ids

@pytest.mark.parametrize('bad',[[0],[2,2],[5,1]])
def test_bad_doc_gaps(bad):
    with pytest.raises(ValueError):to_positive_gaps(bad)

def test_bad_positions():
    with pytest.raises(ValueError):positions_to_gaps([[2,2]])
    with pytest.raises(ValueError):gaps_to_positions([1,2],[1])
    with pytest.raises(ValueError):gaps_to_positions([0],[1])

def test_tamper_header():
    row=list(pack_term([1,2],[[0],[2]],'varint'))
    with pytest.raises(ValueError):unpack_term(0,*row)
    with pytest.raises(ValueError):unpack_term(2,99,*row[1:])
    with pytest.raises(ValueError):unpack_term(3,*row)

def test_full_fixture_end_to_end():
    result=run('fixture',docs=DOCS)
    assert result['round']==112
    assert result['full_vocabulary_terms']>15
    assert result['full_token_occurrences']>1000
    assert result['phrase_query_count']>0
    assert result['bm25_query_count']>15
    for family in FAMILIES:
        m=result['codecs'][family]
        assert m['checks']['all_matched']
        assert m['checks']['max_bm25_score_abs_error']<1e-12
        assert m['checks']['exact_bigram_phrase_queries']>0
        assert m['encoded_position_bytes']>0
        assert m['physical_sqlite_bytes']>=m['encoded_doc_bytes']+m['encoded_position_bytes']+m['encoded_tf_bytes']

def test_selected_doc_positions_and_no_source_leak():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp);db=make_fts(root/'original.sqlite',DOCS)
        p,lengths,samples=collect_positions(db,len(DOCS))
        assert sum(lengths)==sum(sum(map(len,pos)) for _,pos in p.values())
        assert len(samples)==len(DOCS)
        queries,phrases=plan(p,len(DOCS),samples)
        assert phrases
        path=root/'payload.sqlite';meta=build_store(path,p,lengths,'barm_r')
        with sqlite3.connect(path) as store:
            assert fetch(store,'ABSENT')[0]==[]
            assert phrase_match(store,('alpha','beta'))==[int(x[0]) for x in db.execute('SELECT rowid FROM docs WHERE docs MATCH ? ORDER BY rowid',('"alpha beta"',))]
            assert verify(store,db,queries,phrases,lengths)['all_matched']
            # The position BLOB is selected only when requested.
            statement='SELECT df,dtag,ptag,doc_payload,tf_payload FROM postings WHERE term=?'
            assert len(store.execute(statement,('alpha',)).fetchone())==5
        db.close()