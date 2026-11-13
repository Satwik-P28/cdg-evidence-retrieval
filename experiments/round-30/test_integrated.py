"""Round 30 regression tests, including real SQLite and Zstandard bytes."""
from pathlib import Path
import tempfile, unittest, json, sqlite3, os
from integrated import canon, git_blob_sha, run_question, benchmark, load_json


def fixture(bridge=True):
    # Authored smoke fixture, unrelated to HotpotQA and unsuitable for QA claims.
    return {
        'question':'Where was the novelist who wrote The Sapphire Orchard born?' if bridge else 'Were Avery Reed and Nila Kane both novelists?',
        'type':'bridge' if bridge else 'comparison',
        'context':[
            ['The Sapphire Orchard', ['The Sapphire Orchard is a novel written by Avery Reed.', 'It follows a group of botanists searching for a rare blue fruit.']],
            ['Avery Reed', ['Avery Reed was born in the town of Larchfield.', 'She worked as a novelist for several decades.']],
            ['Nila Kane', ['Nila Kane was a novelist and a playwright.', 'She was born in Stonebridge.']],
            ['Larchfield', ['Larchfield is a small town in the north.', 'Its botanical gardens contain sapphire flowers.']],
            ['Botanical novels', ['Botanical novels are popular across the region.', 'Writers often mention birthplaces and gardens.']],
        ],
        'supporting_facts':[['The Sapphire Orchard',0],['Avery Reed',0]] if bridge else [['Avery Reed',1],['Nila Kane',0]],
        '_id':'authored-smoke-fixture'}

class Round30(unittest.TestCase):
    def test_tokenization_unicode(self):self.assertEqual(canon('Avery—référence!'), 'avery référence')
    def test_blob_hash(self):self.assertEqual(git_blob_sha(b'hello'),'b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0')
    def test_invalid_inputs_refused(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'raw.json';p.write_text(json.dumps([fixture()]))
            with self.assertRaises(ValueError):load_json(p,True)
            self.assertEqual(len(load_json(p,False)),1)
    def test_exact_source_reads(self):
        with tempfile.TemporaryDirectory() as d:
            r=run_question(fixture(),'fixed',128,Path(d)/'r')
            self.assertGreater(r['sqlite_bytes'],0)
            self.assertGreater(r['payload_bytes'],0)
            self.assertTrue(r['policies']['fts']['picked_titles'])
            self.assertGreaterEqual(r['edge_count'],1)
    def test_link_index_and_dynamic_agree_on_fixture(self):
        with tempfile.TemporaryDirectory() as d:
            r=run_question(fixture(),'lines',256,Path(d)/'r')
            self.assertEqual(r['policies']['dynamic_bridge']['picked_titles'],r['policies']['link_index']['picked_titles'])
    def test_whole_vs_fixed_exact_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            a=run_question(fixture(),'whole',0,Path(d)/'w')
            b=run_question(fixture(),'fixed',128,Path(d)/'f')
            self.assertEqual(a['policies']['fts']['picked_titles'],b['policies']['fts']['picked_titles'])
    def test_comparison_fixture_never_gold_labels_in_policy(self):
        with tempfile.TemporaryDirectory() as d:
            x=fixture(False)
            a=run_question(x,'fixed',512,Path(d)/'a')
            x['supporting_facts']=[['Nila Kane',0]]
            b=run_question(x,'fixed',512,Path(d)/'b')
            self.assertEqual(a['policies']['fts']['picked_titles'],b['policies']['fts']['picked_titles'])

if __name__=='__main__':unittest.main()
