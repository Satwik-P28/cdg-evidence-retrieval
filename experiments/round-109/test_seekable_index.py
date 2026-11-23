"""R109 seekable exact posting store fixtures and corruption checks."""
import sqlite3,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from seekable_index import run,list_plan,ids_to_gaps,gaps_to_ids,make_store,query_ids,CODECS_COMPARE


def test_fixed_dataset_external_postings_store():
    docs=[('A','alpha beta alpha'),('B','beta gamma'),('C','alpha gamma beta'),
          ('D','delta gamma'),('E','gamma delta alpha')]
    res=run('fixture',docs)
    assert res['num_original_documents']==5
    assert res['selected_term_count']>=4
    assert res['selected_docid_postings']>=5
    assert all(m['term_rows']==res['selected_term_count'] for m in res['metrics'].values())
    assert all(m['lookups']['exact_single_term_queries']>0 for m in res['metrics'].values())
    assert all(m['physical_sqlite_bytes']>=m['encoded_payload_bytes'] for m in res['metrics'].values())


def test_deterministic_source_independent_query_selection():
    terms=['alpha','beta','zeta','theta','omega']
    assert list_plan(terms)==list_plan(terms[::-1])


@pytest.mark.parametrize('codec',CODECS_COMPARE)
def test_explicit_missing_terms_and_corruption(tmp_path,codec):
    path=tmp_path/(codec+'.sqlite')
    make_store(path,{'df1':[('one',[1]),('three',[1,3,8])]},codec)
    db=sqlite3.connect(path)
    try:
        assert query_ids(db,'three',codec)==[1,3,8]
        assert query_ids(db,'missing',codec)==[]
        db.execute('UPDATE postings SET df=999 WHERE term=?',('three',))
        with pytest.raises(ValueError): query_ids(db,'three',codec)
    finally:db.close()


def test_gap_id_round_trip():
    a=[1,2,12,24,105]
    assert gaps_to_ids(ids_to_gaps(a))==a
    with pytest.raises(ValueError):ids_to_gaps([3,2])