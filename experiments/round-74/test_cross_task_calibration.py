import unittest
from cross_task_calibration import (
    partition,response_risks,choose_cutoff,confusion,clustered_interval,
    SALT,TRAIN_QA_SOURCE_GROUPS,TEST_D2T_SOURCE_GROUPS,
    RISK_SCORES,TARGET_TRAIN_FPRS,
)


def fixture_src(sid,task):
    return {'source_id':sid,'task_type':task,
            'source_info':{'question':'Where?','passages':'The answer is Berlin.'}}


def fixture_rsp(sid,typ,index):
    txt='The answer was Paris.'
    left=txt.index('Paris')
    return {
        'id':f'{typ}-{sid}-{index}',
        'source_id':sid,'split':typ,'quality':'good',
        'response':txt,'labels':[{'start':left,'end':left+5,'text':'Paris',
                                  'label_type':'Conflict'}] if index%3==0 else [],
    }


class R74Tests(unittest.TestCase):
    def test_split_is_disjoint_by_source_and_task(self):
        sources=[fixture_src(str(i),'QA') for i in range(40)]
        sources += [fixture_src(str(i),'Data2txt') for i in range(40,60)]
        resp=[]
        for i in range(40):
            resp.extend(fixture_rsp(str(i),'train',j) for j in range(3))
        for i in range(40,60):
            resp.extend(fixture_rsp(str(i),'test',j) for j in range(3))
        train,test,byid,partition_hash=partition(resp,sources)
        self.assertEqual(len({x['source_id'] for x in train}),TRAIN_QA_SOURCE_GROUPS)
        self.assertEqual(len({x['source_id'] for x in test}),TEST_D2T_SOURCE_GROUPS)
        self.assertFalse({x['source_id'] for x in train}&
                         {x['source_id'] for x in test})
        self.assertEqual(len(train),96)
        self.assertEqual(len(test),48)
        self.assertEqual(len(partition_hash['train']['sample_source_ids_sha256']),64)

    def test_frozen_thresholds_and_no_test_gold_selection(self):
        self.assertEqual(TARGET_TRAIN_FPRS,(.10,.25))
        self.assertEqual(set(RISK_SCORES),
                         {'top1_max','top3_max','top3_mean'})
        negative=[.1,.2,.3,.4,.5,.6,.7,.8,.9,1.0]
        t10,f10=choose_cutoff(negative,.1)
        t25,f25=choose_cutoff(negative,.25)
        self.assertLessEqual(f10,.1)
        self.assertLessEqual(f25,.25)
        self.assertGreaterEqual(t10,t25)
        self.assertEqual(sum(x>t10 for x in negative),1)
        with self.assertRaises(ValueError):choose_cutoff([],.1)

    def test_response_score_aggregation_and_gold_noninterference(self):
        cases=[{
            'task':'QA','source_group':'first','response_id':'response',
            'gold':1,'strict_gold':0,'literal_warning':True,
            'pair_indices':{
                'nli_lexical_top1':[0],
                'nli_lexical_top3':[0,1,2]}},
            {
            'task':'QA','source_group':'first','response_id':'response',
            'gold':0,'strict_gold':0,'literal_warning':False,
            'pair_indices':{
                'nli_lexical_top1':[3],
                'nli_lexical_top3':[3,4,5]}},
        ]
        numbers=[.1,.6,.7,.2,.8,.9]
        result=response_risks(cases,numbers)
        self.assertEqual(len(result),1)
        self.assertTrue(result[0]['human_positive'])
        self.assertFalse(result[0]['strict_human_positive'])
        self.assertAlmostEqual(result[0]['scores']['top1_max'],.9)
        self.assertAlmostEqual(result[0]['scores']['top3_max'],.3)
        flipped=[{**case,'gold':0,'strict_gold':0} for case in cases]
        alt=response_risks(flipped,numbers)
        self.assertEqual(result[0]['scores'],alt[0]['scores'])
        self.assertNotEqual(result[0]['human_positive'],alt[0]['human_positive'])

    def test_source_group_bootstrap_respects_shared_responses(self):
        rows=[]
        for j in range(6):
            for k in range(3):
                rows.append({
                    'source_id':str(j),
                    'human_positive':k==0,
                    'strict_human_positive':k==0,
                    'scores':{method:.9 if k==0 else .1 for method in RISK_SCORES},
                    'lexical_warning':k==0,
                })
        observed=confusion(rows,'top3_max',.5)
        self.assertEqual(observed['tp'],6)
        self.assertEqual(observed['fp'],0)
        self.assertEqual(observed['f1'],1)
        self.assertEqual(clustered_interval(rows,'top3_max',.5,reps=100),
                         clustered_interval(rows,'top3_max',.5,reps=100))


if __name__=='__main__':unittest.main()
