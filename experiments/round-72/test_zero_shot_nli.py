import unittest
from zero_shot_nli import (
    TASK_GROUPS,SALT,source_windows,candidate_windows,segment_labels,
    group_sample,compile_cases,score_cases,calculate,ENTAIL_THRESHOLD,
    METHODS,load,R69
)


def src(sid,task,text):
    return {'source_id':sid,'task_type':task,
            'source_info':{'question':'Where was the event?','passages':text}
            if task=='QA' else text}


def response(id,sid,content,has_hallucination=False):
    labels=[]
    if has_hallucination:
        left=content.index('Paris')
        labels=[{'start':left,'end':left+5,'text':'Paris',
                 'label_type':'Evident Conflict'}]
    return {'id':id,'source_id':sid,'response':content,
            'labels':labels,'split':'test','quality':'good'}


class NliIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.r69=load('r69_nli_unit',R69)

    def test_fixed_source_windows_and_source_order(self):
        blob=' '.join('word'+str(i) for i in range(1000))
        wins,total,covered=source_windows(blob)
        self.assertEqual(total,1000)
        self.assertEqual(covered,1000)
        self.assertTrue(wins[0].startswith('word0 '))
        self.assertEqual(len(wins),10)

    def test_lexical_candidate_ranking_has_no_labels(self):
        wins=['The capital is Berlin.','The artist was born in Rome.',
              'The painter painted in Paris.']
        order=candidate_windows(wins,'Where did the artist live?',self.r69)
        self.assertEqual(order[0],1)
        self.assertEqual(sorted(order),[0,1,2])

    def test_human_spans_are_scored_only_after_selection(self):
        a=response('a','s','The inventor moved to Paris.',True)
        b=response('a','s','The inventor moved to Paris.',False)
        self.assertNotEqual(segment_labels(a,self.r69)[0][3],
                            segment_labels(b,self.r69)[0][3])
        source_map={'s':src('s','QA',
                           'The inventor moved to Berlin in 1997.')}
        old=compile_cases([a],source_map,self.r69)
        new=compile_cases([b],source_map,self.r69)
        self.assertEqual(old[1],new[1])
        self.assertEqual(old[0][0]['pair_indices'],new[0][0]['pair_indices'])

    def test_nli_aggregation_and_human_confusion(self):
        r={
            'task':'QA','source_group':'src','response_id':'answer',
            'gold':1,'strict_gold':1,'literal_warning':True,
            'pair_indices':{'nli_first':[0],
                            'nli_lexical_top1':[1],
                            'nli_lexical_top3':[1,2,3]}}
        values=[.11,.12,.22,.91]
        scores=score_cases([r],values,self.r69)
        self.assertTrue(scores[0]['warnings']['nli_first'])
        self.assertTrue(scores[0]['warnings']['nli_lexical_top1'])
        self.assertFalse(scores[0]['warnings']['nli_lexical_top3'])
        metrics=calculate([r],values,self.r69)
        self.assertEqual(metrics['QA']['methods']['nli_first']
                         ['original_human_labels']['response']['tp'],1)
        self.assertEqual(metrics['QA']['methods']['nli_lexical_top3']
                         ['original_human_labels']['response']['fn'],1)
        self.assertEqual(set(scores[0]['warnings']),set(METHODS))
        self.assertEqual(ENTAIL_THRESHOLD,.5)

    def test_task_groups_source_disjoint(self):
        sources=[src(str(i),'QA' if i<8 else 'Summary',
                     'The artist was in Berlin.')
                 for i in range(24)]
        replies=[response('a'+str(i),str(i),'The artist was in Berlin.')
                 for i in range(24)]
        sample,source_map,meta=group_sample(replies,sources)
        self.assertEqual(meta['source_groups'],TASK_GROUPS)
        self.assertEqual(meta['response_count'],24)
        self.assertEqual(len(sample),24)
        self.assertEqual(len(meta['source_ids_sha256']),64)

if __name__=='__main__':
    unittest.main()
