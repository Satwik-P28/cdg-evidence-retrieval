import sqlite3
import tempfile
import unittest
from pathlib import Path
from atomic_source_db import (
    create_db,read,atomic_update,atomic_delete,strict_inflate,
    query,benchmark
)

DOCS=[
    {'doc_id':11,'title':'Plasma astronomy','abstract':['The plasma stream rises above the observed surface.']},
    {'doc_id':22,'title':'Antibiotic response','abstract':['Bacteria resisted the medicine.']},
    {'doc_id':33,'title':'Flight control','abstract':['Signal adjustment is measured.']},
]
CLAIMS=[
    {'id':1,'claim':'Plasma astronomy stream rises.','evidence':{'11':[{'label':'SUPPORT','sentences':[0]}]}},
    {'id':2,'claim':'Antibiotic response bacteria resisted treatment.','evidence':{'22':[{'label':'SUPPORT','sentences':[0]}]}},
]


class AtomicCasTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db,self.meta=create_db(Path(self.temp.name)/'index.sqlite',DOCS)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_source_original_utf8_and_metadata(self):
        row=read(self.db,1)
        self.assertEqual(row['doc_id'],'11')
        self.assertEqual(row['generation'],1)
        self.assertIn(b'Plasma astronomy\n',row['source_bytes'])
        self.assertEqual(query(self.db,'plasma astronomy',1),[1])
        self.assertGreater(self.meta['persistent_index_and_source_bytes'],0)
        self.assertEqual(self.meta['source_count'],3)

    def test_both_injected_update_failures_leave_old_snapshot(self):
        old=read(self.db,1)
        before=query(self.db,'plasma stream')
        for fault in ('after_payload','after_index'):
            with self.assertRaises(RuntimeError):
                atomic_update(self.db,1,'11','Nebula engine',
                              ['The nebula drive accelerates.'],fault)
            self.assertEqual(read(self.db,1),old)
            self.assertEqual(query(self.db,'plasma stream'),before)
            self.assertEqual(query(self.db,'nebula drive'),[])

    def test_successful_update_commits_source_and_index_together(self):
        generation=atomic_update(self.db,1,'11','Nebula engine',
                                 ['The nebula drive accelerates.'])
        self.assertEqual(generation,2)
        self.assertEqual(query(self.db,'nebula drive'),[1])
        self.assertEqual(query(self.db,'plasma stream'),[])
        content=read(self.db,1)
        self.assertEqual(content['source_bytes'],
                         b'Nebula engine\nThe nebula drive accelerates.')
        self.assertEqual(content['generation'],2)
        with self.assertRaises(KeyError):
            atomic_update(self.db,1,'no-such-doc','Oops',['wrong'])

    def test_atomic_delete_failure_and_success(self):
        with self.assertRaises(RuntimeError):
            atomic_delete(self.db,2,'22','after_payload')
        self.assertEqual(read(self.db,2)['doc_id'],'22')
        self.assertEqual(query(self.db,'antibiotic response'),[2])
        atomic_delete(self.db,2,'22')
        with self.assertRaises(KeyError):
            read(self.db,2)
        self.assertEqual(query(self.db,'antibiotic response'),[])

    def test_corrupted_source_rejected(self):
        self.db.execute('BEGIN IMMEDIATE')
        self.db.execute("UPDATE docs SET compressed=? WHERE rowid=1",(b'invalid-zlib-stream',))
        self.db.execute('COMMIT')
        with self.assertRaises(ValueError):
            read(self.db,1)
        with self.assertRaises(ValueError):
            strict_inflate(__import__('zlib').compress(b'valid')+b'unrelated bytes')

    def test_full_rank_and_source_comparison_to_contentful_control(self):
        result=benchmark(DOCS,CLAIMS)
        self.assertTrue(result['top10_rankings_identical_for_all_claims'])
        self.assertEqual(result['source_reads']['top1_docs_read'],2)
        self.assertEqual(result['gold_retrieval']['denominator'],2)
        self.assertEqual(result['gold_retrieval']['recall_at_1']['hits'],2)


if __name__=='__main__':
    unittest.main()
