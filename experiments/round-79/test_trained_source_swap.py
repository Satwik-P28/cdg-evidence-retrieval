import unittest
from trained_source_swap import (
    load,R69,R76,jaccard,select_alternates,context_for_pair,changed,
    aggregate,bootstrap_difference
)


def source(sid,task,text,question='Where?'):
    info={'question':question,'passages':text} if task=='QA' else text
    return {'source_id':sid,'task_type':task,'source_info':info}


class TrainedSourceSwapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r69=load('r69_test79',R69)
        cls.r76=load('r76_test79',R76)

    def test_jaccard_extremes(self):
        self.assertEqual(jaccard({'a','b'},{'a','b'}),1.0)
        self.assertEqual(jaccard({'a'},{'b'}),0.0)

    def test_same_task_nearest_and_farthest_without_response(self):
        byid={
            'q1':source('q1','QA','Berlin scientists studied astronomy.'),
            'q2':source('q2','QA','Berlin scientists studied physics.'),
            'q3':source('q3','QA','Brazil football league champions.'),
            's1':source('s1','Summary','Paris markets stock'),
            's2':source('s2','Summary','Paris banking finance'),
            's3':source('s3','Summary','Tokyo music theater'),
        }
        rows=[{'source_id':sid,'response':'Anything',
               'labels':[{'hallucination':'irrelevant'}]} for sid in byid]
        result=select_alternates(rows,byid,self.r69)
        self.assertEqual(result['q1']['nearest'],'q2')
        self.assertEqual(result['q1']['farthest'],'q3')
        self.assertEqual(result['s1']['nearest'],'s2')
        for sid,choices in result.items():
            self.assertNotEqual(choices['nearest'],sid)
            self.assertNotEqual(choices['farthest'],sid)
            self.assertEqual(byid[sid]['task_type'],
                             byid[choices['nearest']]['task_type'])

    def test_question_stays_fixed_during_qa_swap(self):
        byid={
            'a':source('a','QA','Passage 1: Paris.','What is the capital?'),
            'b':source('b','QA','Passage 1: Kyoto.','Where is Kyoto?'),
        }
        got,question=context_for_pair('a','b',byid,self.r69,self.r76)
        self.assertEqual(question,'What is the capital?')
        self.assertTrue('Kyoto' in ' '.join(got))
        self.assertFalse('Paris' in ' '.join(got))
        with self.assertRaises(ValueError):
            context_for_pair('a','s',dict(byid,s=source('s','Summary','Tokyo')),
                             self.r69,self.r76)

    def test_mask_change_separate_from_source_correctness(self):
        self.assertEqual(changed([False,True],[True,True]),
                         {'response_flag_changed':0,'character_change_rate':0.5,
                          'flagged_char_delta':1})
        self.assertEqual(changed([False,False],[False,True])
                         ['response_flag_changed'],1)
        with self.assertRaises(ValueError):
            changed([True],[True,False])

    def test_grouped_bootstrap_deterministic(self):
        rows=[]
        for sid in ('a','b','c'):
            for i in range(3):
                rows.append({
                    'source_id':sid,'task':'QA','original_positive':0,
                    'nearest':{'response_flag_changed':int(sid=='a'),
                               'character_change_rate':0.,'flagged_char_delta':0},
                    'farthest':{'response_flag_changed':int(sid!='a'),
                                'character_change_rate':.1,'flagged_char_delta':1},
                })
        left=bootstrap_difference(rows,reps=50,seed=7)
        right=bootstrap_difference(rows,reps=50,seed=7)
        self.assertEqual(left,right)
        self.assertEqual(aggregate(rows)['all']['responses'],9)


if __name__=='__main__':
    unittest.main()
