import copy
import unittest
from source_swap import (
    counterfactual_map,collect_per_response,group_ci,load,R69,
    SOURCE_SWAP_RULE,
)


def source(sid,city):
    return {'source_id':sid,'task_type':'Data2txt',
            'source_info':{'name':'A cafe','city':city,
                           'categories':['coffee','breakfast'],
                           'phone':'12345','description':'Coffee and breakfast'}}


class SourceSwapTests(unittest.TestCase):
    def setUp(self):
        self.r69=load('r69_unit75',R69)
        self.mapping={
            'a':source('a','Berlin'),
            'b':source('b','Paris'),
            'c':source('c','Tokyo'),
        }

    def test_counterfactual_excludes_self_and_uses_only_source(self):
        chosen,overlap=counterfactual_map(
            self.mapping,set(self.mapping),self.r69)
        self.assertEqual(set(chosen),set(self.mapping))
        self.assertTrue(all(chosen[k]!=k for k in chosen))
        self.assertTrue(all(0<=x<=1 for x in overlap.values()))
        changed={k:copy.deepcopy(v) for k,v in self.mapping.items()}
        chosen2,overlap2=counterfactual_map(changed,set(changed),self.r69)
        self.assertEqual((chosen,overlap),(chosen2,overlap2))
        self.assertIn('distinct Data2txt',SOURCE_SWAP_RULE)

    def test_missing_comparator_fails_closed(self):
        with self.assertRaises(ValueError):
            counterfactual_map(self.mapping,{'a'},self.r69)

    def test_response_aligned_score_pairs(self):
        cases=[{
            'response_id':'r1','source_group':'a','gold':1,'strict_gold':0,
            'pair_indices':{'nli_lexical_top3':[0,1]},
        },{
            'response_id':'r1','source_group':'a','gold':0,'strict_gold':0,
            'pair_indices':{'nli_lexical_top3':[2,3]},
        },{
            'response_id':'r2','source_group':'b','gold':0,'strict_gold':0,
            'pair_indices':{'nli_lexical_top3':[4]},
        }]
        result=collect_per_response(cases,[.1,.8,.2,.9,.5])
        self.assertEqual(set(result),{'r1','r2'})
        self.assertEqual(result['r1']['claims'],2)
        self.assertEqual(result['r1']['min_entailment'],.8)
        self.assertTrue(result['r1']['gold'])
        self.assertFalse(result['r2']['gold'])
        unlabeled=[{**x,'gold':0,'strict_gold':0} for x in cases]
        different=collect_per_response(unlabeled,[.1,.8,.2,.9,.5])
        self.assertEqual(result['r1']['min_entailment'],
                         different['r1']['min_entailment'])
        self.assertNotEqual(result['r1']['gold'],different['r1']['gold'])

    def test_group_bootstrap_not_response_iid(self):
        rows=[{'source_id':str(i),'delta_min_entailment':.1*i}
              for i in range(5) for _ in range(3)]
        a=group_ci(rows,reps=200)
        b=group_ci(rows,reps=200)
        self.assertEqual(a,b)
        self.assertLessEqual(a[0],a[1])
        self.assertTrue(a[0]>=0)


if __name__=='__main__':unittest.main()
