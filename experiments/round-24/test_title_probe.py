import json
import tempfile
import unittest
from pathlib import Path
from title_probe import words, git_blob_sha, evaluate, load

class TitleProbeTests(unittest.TestCase):
    def test_unicode_tokenization(self):
        self.assertEqual(words('Marie Cécile / Prussia_1900'),['marie','cécile','prussia','1900'])

    def test_git_blob_hash(self):
        import hashlib
        self.assertEqual(git_blob_sha(b'abc'),hashlib.sha1(b'blob 3\0abc').hexdigest())

    def test_source_hash_failure(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'dev_questions.json'
            p.write_text('[]')
            with self.assertRaises(ValueError):load(p)

    def test_no_gold_used_in_ranking_query(self):
        a={'question':'Where was Alpha Alpha written?', 'supporting_titles':['Alpha Alpha','Hidden Bridge'], 'type':'bridge'}
        b={'question':'Compare Beta Beta and Gamma Gamma', 'supporting_titles':['Beta Beta','Gamma Gamma'],'type':'comparison'}
        out=evaluate([a],[b])
        self.assertEqual(out['title_count'],4)
        self.assertEqual(out['subsets']['dev']['all']['n'],1)
        self.assertEqual(out['subsets']['test']['all']['n'],1)

if __name__ == '__main__':unittest.main()
