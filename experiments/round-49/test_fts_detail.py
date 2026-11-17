import sqlite3
import tempfile
import unittest
from pathlib import Path
from fts_detail import Index,CONFIGS,experiment,load_versions


class TestIndexDetail(unittest.TestCase):
    def test_all_modes_preserve_keyword_row_set(self):
        texts=['café evidence\npython package manager\n'.encode(),
               b'evidence source\nnew package manager\n']
        with tempfile.TemporaryDirectory() as home:
            indexes=[Index(Path(home)/f'{k}.db',texts,k) for k in CONFIGS]
            for e in indexes:
                self.assertEqual(len(e.matches(0,'evidence')),1)
                self.assertEqual(len(e.matches(1,'evidence')),1)
                self.assertEqual(e.matches(0,'evidence')[0][1:],(0,len('café evidence\n'.encode())))
                e.close()

    def test_full_supports_phrase_and_sparse_may_reject(self):
        with tempfile.TemporaryDirectory() as home:
            texts=[b'python package manager\nanother package manager\n']
            full=Index(Path(home)/'full.sqlite',texts,'full')
            low=Index(Path(home)/'small.sqlite',texts,'none')
            try:
                self.assertEqual(len(full.matches(0,'"python package"')),1)
                try:
                    result=low.matches(0,'"python package"')
                    self.assertLessEqual(len(result),1)
                except sqlite3.OperationalError:
                    pass
            finally:
                full.close();low.close()

    def test_real_history_footprints(self):
        texts=load_versions()
        output=experiment(texts)
        self.assertEqual(output['versions'],12)
        self.assertEqual(len(output['configurations']),6)
        for stat in output['configurations'].values():
            self.assertTrue(stat['keyword_match_parity'])
        self.assertLessEqual(output['configurations']['none_no_columnsize']['index_bytes'],
                             output['configurations']['full']['index_bytes'])
        self.assertEqual(output['configurations']['full']['bm25_exact_top3_order_matches'],120)
        self.assertEqual(output['configurations']['full']['mean_top3_overlap_with_full_bm25'],1.0)

if __name__=='__main__':
    unittest.main()
