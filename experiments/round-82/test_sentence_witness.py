import unittest
from sentence_witness import (
    candidate_plan, source_sentences, prepare_cases, confusion, score,
    POLICIES, R80_SHA, R81_SHA
)


def words(t):
    import re
    return re.findall(r'[A-Za-z]+',t.lower())


class SentenceWitnessTests(unittest.TestCase):
    def test_source_sentence_split_and_adjacent_evidence(self):
        src='Registry check. A is the supervisor of B. B does not supervise A.'
        plan=candidate_plan(src,'A supervises B.',words)
        self.assertEqual(plan['sentences'],3)
        self.assertEqual(len(plan['policies']['best_single']),3)
        self.assertEqual(len(plan['policies']['best_adjacent2']),2)
        self.assertEqual(len(plan['policies']['full']),1)
        self.assertEqual(
            [plan['windows'][i] for i in plan['policies']['full']],[src])
        self.assertEqual(
            len(plan['policies']['single_or_adjacent2']),5)
        self.assertTrue(all(
            0<=i<len(plan['windows'])
            for values in plan['policies'].values() for i in values))

    def test_plan_independent_of_fixture_truth(self):
        src='Fictional document. A supervises B. B does not supervise A.'
        a=candidate_plan(src,'A supervises B.',words)
        b=candidate_plan(src,'A supervises B.',words)
        self.assertEqual(a,b)
        self.assertEqual(set(a['policies']),set(POLICIES))

    def test_original_fixtures_exact_byte_receipts_and_identity(self):
        cases,arch=prepare_cases()
        self.assertEqual(len(cases),220)
        self.assertEqual(len([x for x in cases if x['suite']=='R80']),120)
        self.assertEqual(len([x for x in cases if x['suite']=='R81']),100)
        self.assertEqual(arch['R80']['verified_receipts'],240)
        self.assertEqual(arch['R81']['verified_receipts'],200)
        self.assertEqual(sum(c['supported'] for c in cases),100)
        self.assertTrue(all(c['doc'].strip() and c['claim'].strip()
                            for c in cases))
        self.assertEqual(len(R80_SHA),64)
        self.assertEqual(len(R81_SHA),64)

    def test_paired_confusion_transition_error_accounting(self):
        cases=[
            {'suite':'R80','condition':'a','entity_group':'e0',
             'state':'supported','supported':True},
            {'suite':'R80','condition':'a','entity_group':'e0',
             'state':'unknown','supported':False},
            {'suite':'R81','condition':'b','entity_group':'e1',
             'state':'supported','supported':True},
            {'suite':'R81','condition':'b','entity_group':'e1',
             'state':'contradicted','supported':False},
        ]
        baseline=[0,0,1,1]
        improved=[1,0,1,0]
        outcomes,transitions=score(cases,{
            'full':baseline,'best_single':improved
        })
        self.assertEqual(confusion(cases,improved),
                         {'n':4,'tp':2,'fp':0,'fn':0,'tn':2,
                          'balanced_accuracy':1.,
                          'support_recall':1.,'unsupported_rejection':1.})
        self.assertEqual(transitions['best_single']['all']
                         ['full_wrong_to_policy_correct'],2)
        self.assertEqual(transitions['best_single']['all']
                         ['full_correct_to_policy_wrong'],0)
        self.assertEqual(outcomes['best_single']['R81']['tp'],1)


if __name__=='__main__':
    unittest.main()
