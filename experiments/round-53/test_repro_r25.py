import json
import unittest
from pathlib import Path
from repro_r25 import compact,evaluate,loader,HISTORIC


class R53Tests(unittest.TestCase):
    def test_pinned_original_source_and_metrics(self):
        mod=loader()
        self.assertEqual(mod.BLOB_SHA,'7dbdf068a437f0577043667ffee3a20f0a602154')
        prior=json.loads(HISTORIC.read_text())
        self.assertEqual(prior['corpus']['questions'],100)

    def test_synthetic_no_gold_leakage_and_contract(self):
        sample=[{
            '_id':'fixture','type':'bridge',
            'question':'Which film did Founder direct?',
            'context':[
                ['Founder',['The Founder directed Film B.']],
                ['Film B',['Film B was released.']],
                ['Film A',['Unrelated movie']]
            ],
            'supporting_facts':[['Founder',0],['Film B',0]]
        }]
        old={'corpus':{'questions':1},
             'paired_complete_docs':{'2':{'both':0,'bm25_only':0,'bridge_only':0,'neither':1},
                                     '3':{'both':0,'bm25_only':0,'bridge_only':0,'neither':1},
                                     '5':{'both':0,'bm25_only':0,'bridge_only':0,'neither':1}},
             'methods':{m:{str(k):{'all':{'complete_docs':0,'complete_gold_sentences_with_top2_per_document':0}}
                           for k in (2,3,5)} for m in ('bm25','bridge','mmr')}}
        result=evaluate(sample,old)
        self.assertEqual(result['observed']['questions'],1)
        self.assertEqual(result['source_git_blob_sha'],loader().BLOB_SHA)
        self.assertFalse(result['cross_implementation_equal'])
        self.assertTrue(result['mismatches'])

if __name__=='__main__':
    unittest.main()
