import unittest
from contentless_cas import (
    document_bytes,make_fts,query_text,query_fts,compute_rankings,
    validate_ranks,label_recall,compare
)
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3


DOCS=[
    {'doc_id':111,'title':'Plasma membrane','abstract':['Experimental plasma membrane transport.']},
    {'doc_id':222,'title':'Antibiotic resistance','abstract':['The treatment is ineffective.']},
    {'doc_id':333,'title':'Additional cell analysis','abstract':['A different molecule is studied.']},
]
CLAIMS=[
    {'id':1,'claim':'Plasma membrane transport occurs.','evidence':{'111':[{'label':'SUPPORT','sentences':[0]}]}},
    {'id':2,'claim':'Antibiotic resistance is observed.','evidence':{'222':[{'label':'SUPPORT','sentences':[0]}]}},
    {'id':3,'claim':'Cell processes exist.','evidence':{}},
]


class ContentlessCasTests(unittest.TestCase):
    def test_source_serialization_is_exact_and_unicode_safe(self):
        row={'title':'Éléments 北京','abstract':['α one.', 'Beta two.']}
        self.assertEqual(document_bytes(row),'Éléments 北京\nα one. Beta two.'.encode('utf8'))

    def test_contentless_returns_no_original_text(self):
        with TemporaryDirectory() as directory:
            full,fullm=make_fts(Path(directory)/'a.sqlite',DOCS,False)
            lean,leanm=make_fts(Path(directory)/'b.sqlite',DOCS,True)
            try:
                self.assertEqual(
                    full.execute('SELECT title FROM sources WHERE rowid=1').fetchone(),
                    ('Plasma membrane',))
                self.assertEqual(
                    lean.execute('SELECT title,abstract FROM sources WHERE rowid=1').fetchone(),
                    (None,None))
                self.assertGreater(fullm['database_bytes'],0)
                self.assertGreater(leanm['database_bytes'],0)
                self.assertEqual(query_fts(full,CLAIMS[0]['claim']),
                                 query_fts(lean,CLAIMS[0]['claim']))
            finally:
                full.close();lean.close()

    def test_all_ranking_and_recovered_sha_bytes_unchanged(self):
        report=compare(DOCS,CLAIMS)
        self.assertTrue(report['all_top10_rowid_rankings_identical'])
        self.assertEqual(report['archive']['verified_top1_source_reads'],3)
        self.assertEqual(report['gold_evidence_recall']['denominator'],2)
        self.assertEqual(report['gold_evidence_recall']['recall_at_1']['hits'],2)
        self.assertGreater(report['archive']['persistent_whole_zlib_CAS_with_manifest_bytes'],0)
        self.assertGreater(report['retained_size_comparison']['full_fts_plus_archive_duplicate_source_bytes'],
                           report['retained_size_comparison']['full_fts_alone'])

    def test_drift_in_rank_detected(self):
        with self.assertRaises(AssertionError):
            validate_ranks({'a':[1,2]},{'a':[2,1]})
        with self.assertRaises(AssertionError):
            validate_ranks({'a':[1]},{'b':[1]})

    def test_source_query_uses_only_claim_tokens_not_labels(self):
        a=dict(CLAIMS[0])
        b=dict(a,evidence={},claim=a['claim'])
        self.assertEqual(query_text(a['claim']),query_text(b['claim']))
        self.assertIsNone(query_text('the and or were to'))
        self.assertIn('"plasma"',query_text('Plasma membrane.'))
        self.assertNotIn(' OR "or"',query_text('Plasma or membrane.'))


if __name__=='__main__':
    unittest.main()
