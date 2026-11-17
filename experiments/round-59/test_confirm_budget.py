import unittest
from confirm_budget import paired_interval,exact_pvalue,evaluate,ALLOCATORS,PRIMARY,REFERENCE


def row(id,gold=True):
    return {'_id':id,'question':'Which film did Founder direct?',
            'context':[
                ['Founder',['Founder directed Film B.','Additional detail.']],
                ['Film B',['Film B was produced.']],
                ['Film C',['A third movie.']],
                ['Film D',['A fourth movie.']],
                ['Film E',['A fifth movie.']]],
            'supporting_facts':([['Founder',0],['Film B',0]] if gold else [['Film E',0]]),
            'answer':'Film B','type':'bridge'}


class ConfirmationTests(unittest.TestCase):
    def test_exact_discordance(self):
        self.assertEqual(exact_pvalue(3,0),.25)
        self.assertEqual(exact_pvalue(0,0),1.0)
        self.assertEqual(exact_pvalue(2,2),1.0)

    def test_bootstrap_is_deterministic_and_paired(self):
        a=[1,1,1,0,0,1]
        b=[0,1,0,1,0,1]
        output=paired_interval(a,b,reps=1000)
        self.assertEqual(output,paired_interval(a,b,reps=1000))
        self.assertEqual(output['net_gain_count'],1)
        self.assertEqual(sum(output[k] for k in ('left_only','right_only','both','neither')),6)

    def test_result_structure_and_no_policy_label_leak(self):
        first=evaluate([row('a'),row('b',False)])
        second=evaluate([row('a',False),row('b')])
        self.assertEqual(first['questions'],2)
        self.assertEqual(first['primary_comparison'],PRIMARY+'_vs_'+REFERENCE)
        self.assertEqual(set(first['methods']),set(ALLOCATORS))
        for method in ALLOCATORS:
            self.assertEqual(first['methods'][method]['n'],2)
            # Same contexts and question. Gold assignment cannot change retrieval,
            # selected sentence counts, or frame traffic.
            self.assertEqual(first['methods'][method]['mean_sentences'],
                             second['methods'][method]['mean_sentences'])
            self.assertEqual(first['methods'][method]['mean_gear_frame_bytes'],
                             second['methods'][method]['mean_gear_frame_bytes'])

if __name__=='__main__':
    unittest.main()
