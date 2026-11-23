from pathlib import Path
from tempfile import TemporaryDirectory
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fts5_postings import load_paragraphs, postings_from_docs, sizes_for_list, run


def test_actual_sqlite_fts5_posting_dedup_and_gaps():
    docs=['alpha beta alpha', 'beta gamma', 'alpha gamma', 'alpha delta gamma']
    index=postings_from_docs(docs)
    assert index['alpha']==[1,3,4]
    assert index['beta']==[1,2]
    assert sizes_for_list(index['alpha'])['barm_r']>0


def test_markdown_corpus_with_disjoint_checked_source_bytes():
    with TemporaryDirectory() as d:
        root=Path(d)
        (root/'a.md').write_text('alpha beta gamma\n\nalpha delta epsilon\n\nbeta gamma delta\n')
        (root/'b.md').write_text('alpha gamma epsilon\n\nalpha beta gamma\n\nalpha beta delta\n')
        res=run(root,['*.md'],min_df=2,max_files=2,max_terms=100)
        assert res['n_documents']==6
        assert res['n_measured_terms']>0
        assert res['sizes_bytes']['barm_r']>0
        assert all(len(row['sha256'])==64 for row in res['input_manifest'])


def test_fails_on_missing_corpus():
    with TemporaryDirectory() as d:
        try:
            run(Path(d),['*.md'])
        except ValueError:
            return
        raise AssertionError('empty input must be rejected')