import unittest
from sentence_policy import (rank_sentences,spans,frame_ids,evaluate,
                             METHODS,BUDGETS,K_VALUES,load,R25)


class SentencePolicyTests(unittest.TestCase):
    def setUp(self):
        self.helper=load('cdg_r25_unit56',R25)
        self.sentences=[
            'A movie was made in California.',
            'The filmmaker directed Film B in 1983.',
            'An unrelated description of another title.',
            'Film B was an award-winning work.',
        ]

    def test_span_byte_offsets_preserve_utf8(self):
        source=['café 😊 was here.',' Film B launched.']
        offsets=spans(source)
        raw=''.join(source).encode()
        for sid,start,end in offsets:
            self.assertEqual(raw[start:end],source[sid].encode())

    def test_link_priority_and_no_label_access(self):
        local=rank_sentences('Where did the filmmaker work?',self.sentences,
                             ['Filmmaker','Film B'],'Filmmaker',0,0,
                             'local_bm25',[],self.helper)
        linked=rank_sentences('Where did the filmmaker work?',self.sentences,
                              ['Filmmaker','Film B'],'Filmmaker',0,0,
                              'mention_first',[],self.helper)
        self.assertEqual(sorted(local),list(range(4)))
        self.assertEqual(sorted(linked),list(range(4)))
        self.assertIn(linked[0],(1,3))
        self.assertEqual(linked,rank_sentences(
            'Where did the filmmaker work?',self.sentences,
            ['Filmmaker','Film B'],'Filmmaker',0,0,
            'mention_first',[],self.helper))

    def test_all_methods_are_full_permutations(self):
        for method in METHODS:
            ids=rank_sentences('film director',self.sentences,
                               ['A','Film B'],'A',1,1,
                               method,[(1,10,30),(0,0,10)],self.helper)
            self.assertEqual(sorted(ids),[0,1,2,3])
        self.assertEqual(BUDGETS[-1],999)

    def test_frame_touch_dedup(self):
        manifest={'sha':'x','size':8,
                  'frames':[{'sha':'a','len':4},{'sha':'b','len':4}]}
        self.assertEqual(frame_ids(manifest,1,7),{'a','b'})
        self.assertEqual(frame_ids(manifest,0,3),{'a'})
        self.assertEqual(frame_ids(manifest,0,0),set())

    def test_integrated_small_fixture_and_full_upper_bound(self):
        def row(t):
            return {'_id':t,'question':'Which film did Founder direct?',
                    'context':[
                        ['Founder',['Founder directed Film B.','Another fact.']],
                        ['Film B',['Film B was directed by Founder.']],
                        ['Film C',['Unrelated film C.']],
                        ['Film D',['Unrelated film D.']],
                        ['Film E',['Unrelated film E.']]],
                    'supporting_facts':[['Founder',0],['Film B',0]],
                    'type':'bridge','answer':'Film B'}
        data=evaluate([row('a'),row('b')])
        self.assertEqual(data['sample_size'],2)
        self.assertEqual(len(data['metrics']),len(METHODS)*len(BUDGETS)*len(K_VALUES)*2)
        for result in data['metrics']:
            self.assertLessEqual(result['complete_gold_sentences'],result['complete_gold_docs'])
            self.assertEqual(result['questions'],2)
        for policy in ('bm25','bridge'):
            for k in K_VALUES:
                upper=next(x['complete_gold_docs'] for x in data['metrics']
                           if x['policy']==policy and x['k']==k)
                for metric in data['metrics']:
                    if metric['policy']==policy and metric['k']==k and metric['sentence_budget']==999:
                        self.assertEqual(metric['complete_gold_sentences'],upper)

if __name__=='__main__':
    unittest.main()
