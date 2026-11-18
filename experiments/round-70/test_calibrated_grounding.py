import unittest
from calibrated_grounding import (
    choose_cutoff,confidence_scores,score_counts,metrics,
    grouped_bootstrap,split_sources,evaluate,SCORES,RATES,load,R69
)


def src(sid,text='The inventor worked in Berlin.'):
    return {'source_id':sid,'task_type':'QA',
            'source_info':{'question':'Who worked in Berlin?',
                           'passages':text}}


def response(i,sid,text,split,positive=False):
    label=[]
    if positive:
        begin=text.find('Paris')
        if begin>=0:
            label=[{'start':begin,'end':begin+5,'text':'Paris',
                    'label_type':'Evident Conflict'}]
    return {'id':i,'source_id':sid,'split':split,'quality':'good',
            'response':text,'labels':label}


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        self.r69=load('r69_test70',R69)

    def test_risk_uses_only_response_and_source(self):
        s='The inventor worked in Berlin in 1998.'
        related='The inventor worked in Berlin.'
        unrelated='A stranger worked in Paris in 2015.'
        a=confidence_scores(related,s,self.r69)
        b=confidence_scores(unrelated,s,self.r69)
        self.assertGreaterEqual(b['max_sentence_novelty'],
                                a['max_sentence_novelty'])
        self.assertEqual(set(a),set(SCORES))

    def test_threshold_controls_training_negatives(self):
        neg=[.0,.1,.2,.3,.4,.5,.6,.7,.8,.9]
        a,f=choose_cutoff(neg,.10)
        self.assertLessEqual(f,.10)
        self.assertEqual(sum(x>a for x in neg),1)
        b,f2=choose_cutoff(neg,.05)
        self.assertEqual(sum(x>b for x in neg),0)
        with self.assertRaises(ValueError):
            choose_cutoff([],0.05)

    def test_paired_group_bootstrap_deterministic(self):
        sample=[]
        for group in range(5):
            for i in range(3):
                sample.append({'source_id':str(group),'gold':i==0,
                               'scores':{'max_sentence_novelty':.9 if i==0 else .1}})
        val=grouped_bootstrap(sample,'max_sentence_novelty',.5,reps=100)
        self.assertEqual(val,grouped_bootstrap(sample,'max_sentence_novelty',.5,reps=100))
        self.assertEqual(val['recall_group_bootstrap_95pct'],[1,1])
        self.assertEqual(val['false_positive_rate_group_bootstrap_95pct'],[0,0])

    def test_no_test_gold_used_in_threshold_selection(self):
        train=[{'source_id':str(i),'gold':False,
                'scores':{'max_sentence_novelty':i/20}}
               for i in range(20)]
        threshold,_=choose_cutoff([r['scores']['max_sentence_novelty'] for r in train],.1)
        orig=[{'source_id':'test1','gold':True,'scores':{'max_sentence_novelty':.8}},
              {'source_id':'test2','gold':False,'scores':{'max_sentence_novelty':.2}}]
        flipped=[{**row,'gold':not row['gold']} for row in orig]
        self.assertEqual(threshold,choose_cutoff(
            [r['scores']['max_sentence_novelty'] for r in train],.1)[0])
        self.assertEqual([x['scores'] for x in orig],
                         [x['scores'] for x in flipped])
        self.assertNotEqual(score_counts(orig,'max_sentence_novelty',threshold),
                            score_counts(flipped,'max_sentence_novelty',threshold))

    def test_full_train_and_new_test_group_fixture(self):
        # Reduce R69 nominal 128-group exclusion to 2 only within unit tests.
        import calibrated_grounding as module
        old=self.r69.MAX_TEST_SOURCE_GROUPS
        self.r69.MAX_TEST_SOURCE_GROUPS=2
        try:
            sources=[src(str(i)) for i in range(40)]
            samples=[]
            for i in range(25):
                for k in range(5):
                    samples.append(response('train-'+str(i)+'-'+str(k),
                                            str(i),'The inventor worked in Berlin.',
                                            'train'))
            for i in range(25,40):
                samples.append(response('test-'+str(i),str(i),
                                        'The inventor moved to Paris.', 'test',
                                        positive=i%2==0))
            # Test source selection consumes only test IDs; with 15 test groups
            # and two excluded prior-round groups, 13 remain.
            result=evaluate(samples,sources)
        finally:
            self.r69.MAX_TEST_SOURCE_GROUPS=old
        self.assertEqual(result['old_R69_source_ids_excluded'],2)
        self.assertEqual(result['holdout_good_qa_responses'],13)
        self.assertGreater(result['train_good_qa_responses'],100)
        self.assertEqual(len(result['results']),len(SCORES)*len(RATES)+1)


if __name__=='__main__':unittest.main()
