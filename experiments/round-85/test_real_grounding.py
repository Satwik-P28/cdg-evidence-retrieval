import unittest
from real_grounding import (
    best_lexical_two,input_text,train_threshold,confusion,auroc,evaluate,
    bootstrap_delta,build_inputs,ROUTES
)


def case(split,index,label):
    return {
        'key':f'{split}:{index}:doc{index}:{"SUPPORT" if label else "CONTRADICT"}',
        'split':split,
        'claim_id':str(index),
        'doc_id':f'doc{index}',
        'gold':label,
        'title':'Scientific study',
        'claim':'Plasma rates increase in group A.',
        'sentences':['Nothing about this claim.',
                     'The group A had increased plasma rates.',
                     'Discussion of different material.'],
        'rationale':'The group A had increased plasma rates.',
        'doc':'Title: Scientific study\nAbstract: Nothing about this claim. The group A had increased plasma rates. Discussion of different material.',
    }


class SciFactGroundingTests(unittest.TestCase):
    def test_lexical_selection_ignores_gold_and_rationale(self):
        c=case('train',0,1)
        ix=best_lexical_two(c)
        neg=dict(c,gold=0,rationale='A gold label is not a sentence.')
        self.assertEqual(ix,best_lexical_two(neg))
        self.assertEqual(len(ix),2)
        self.assertIn(1,ix)

    def test_full_lexical_oracle_routes_are_distinct_and_frozen(self):
        c=case('dev',1,1)
        contexts={r:input_text(c,r) for r in ROUTES}
        self.assertEqual(contexts['full'],c['doc'])
        self.assertIn(c['rationale'],contexts['oracle_rationale'])
        self.assertIn(c['rationale'],contexts['lexical2'])
        self.assertEqual(len(build_inputs([c],[case('dev',2,0)])),6)

    def test_binary_confusion_and_auroc(self):
        labels=[1,1,0,0]
        scores=[.9,.4,.2,.7]
        self.assertEqual(confusion(labels,scores,.5)['balanced_accuracy'],.5)
        self.assertEqual(auroc([1,0],[.9,.1]),1.0)
        self.assertEqual(auroc([1,0],[.2,.8]),0.0)
        with self.assertRaises(ValueError):
            confusion([],[],.5)

    def test_train_only_threshold_target(self):
        gold=[1,1,0,0,0,0,0,0,0,0,0,0,0,0]
        probs=[.7,.4,.9,.8,.6,.5,.4,.3,.2,.1,.05,.07,.09,.11]
        # 10% FPR on 12 negatives allows at most one false accept.
        t=train_threshold(gold,probs,.10)
        neg=[p for y,p in zip(gold,probs) if not y]
        self.assertLessEqual(sum(x>t for x in neg),1)
        self.assertGreaterEqual(t,0)

    def test_paired_group_uncertainty_nontrivial_no_label_access(self):
        train=[case('train',i,int(i%2==0)) for i in range(20)]
        dev=[case('dev',i+100,int(i%2==0)) for i in range(20)]
        expanded=build_inputs(train,dev)
        probs=[]
        for x in expanded:
            p=.85 if x['gold'] else .12
            if x['route']=='lexical2' and x['key'].endswith('SUPPORT') and int(x['claim_id'])%5==0:
                p=.15
            probs.append(p)
        result=evaluate(expanded,probs)
        x=bootstrap_delta(expanded,result,alternative='lexical2')
        self.assertEqual(len(x['claim_group_bootstrap_95ci']),2)
        self.assertEqual(x['distinct_dev_claim_groups'],20)
        self.assertLessEqual(x['delta_balanced_accuracy_alternative_minus_full'],0)


if __name__=='__main__':
    unittest.main()
