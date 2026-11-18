import unittest
from semantic_nli import (
    MAX_PREMISES,MAX_CLAIMS,MODEL,MODEL_REVISION,
    source_segments,select_premises,claim_rows,score_from_entailments,
    metric,group_bootstrap,dynamic,R69,
)


def source():
    return {'source_id':'x','task_type':'QA',
            'source_info':{'question':'Where was the inventor?',
                           'passages':'passage 1: The inventor lived in Berlin in 2015.\n'
                                      'passage 2: The artist was born in Paris in 1900.'}}


def response(text,labels=None):
    return {'id':'one','source_id':'x','response':text,'labels':labels or [],
            'quality':'good','split':'test'}


class NliTests(unittest.TestCase):
    def setUp(self):
        self.r69=dynamic('r69_test_72',R69)

    def test_full_commit_and_bound(self):
        self.assertEqual(len(MODEL_REVISION),40)
        self.assertIn('MiniLM',MODEL)
        self.assertEqual(MAX_PREMISES,3)
        self.assertEqual(MAX_CLAIMS,8)

    def test_window_ranking_does_not_use_gold(self):
        base=source()['source_info']['passages']
        windows=select_premises(base,'The inventor lived in Berlin.',self.r69)
        self.assertGreater(len(windows),0)
        self.assertIn('inventor',windows[0].lower())
        self.assertEqual(windows,select_premises(base,
                         'The inventor lived in Berlin.',self.r69))
        self.assertTrue(all(len(s)<=700 for s in source_segments(base)))

    def test_nli_pair_count_and_label_independence(self):
        content='The inventor lived in Rome in 2020.'
        pos=content.index('Rome')
        a=response(content,[{'start':pos,'end':pos+4,
                              'text':'Rome','label_type':'Evident Conflict'}])
        b=response(content,[])
        source_by_id={'x':source()}
        pa,ra=claim_rows([a],source_by_id,self.r69)
        pb,rb=claim_rows([b],source_by_id,self.r69)
        self.assertEqual(pa,pb)
        self.assertEqual(ra[0]['parts'],rb[0]['parts'])
        self.assertNotEqual(ra[0]['human_positive'],rb[0]['human_positive'])

    def test_nli_score_shapes_and_zero_gold_leakage(self):
        a=response('The inventor lived in Rome in 2020.')
        pairs,records=claim_rows([a],{'x':source()},self.r69)
        self.assertGreater(len(pairs),0)
        # Preselected premise list order is deterministic, model-free.
        low,conf=score_from_entailments([.1]*len(pairs),records,self.r69)
        high,_=score_from_entailments([.95]*len(pairs),records,self.r69)
        self.assertTrue(low['nli_top1_50'][0]['pred'])
        self.assertFalse(high['nli_top1_50'][0]['pred'])
        self.assertFalse(high['nli_top3_80'][0]['pred'])
        self.assertEqual(low['nli_top1_50'][0]['source_id'],'x')
        with self.assertRaises(AssertionError):
            score_from_entailments([.1]*(len(pairs)-1),records,self.r69)

    def test_response_confusion_is_not_calibrated_support(self):
        cases=[
            {'source_id':'s1','pred':True,'gold':True,'strict_gold':False},
            {'source_id':'s1','pred':False,'gold':True,'strict_gold':True},
            {'source_id':'s2','pred':True,'gold':False,'strict_gold':False},
            {'source_id':'s2','pred':False,'gold':False,'strict_gold':False},
        ]
        m=metric(cases)
        self.assertEqual((m['tp'],m['fp'],m['fn'],m['tn']),(1,1,1,1))
        self.assertEqual(m['f1'],.5)
        self.assertEqual(metric(cases,strict=True)['tp'],0)
        self.assertEqual(group_bootstrap(cases,reps=30,seed=20),
                         group_bootstrap(cases,reps=30,seed=20))


if __name__=='__main__':unittest.main()
