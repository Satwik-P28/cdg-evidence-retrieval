import unittest
from relation_ablation import (
    VARIANTS,SUPPORT,CONTRA,UNKNOWN,make_case,sample,by_variant
)
from controlled_facts import NAME_PAIRS


class DirectionalityAblationTests(unittest.TestCase):
    def test_same_claim_across_all_ten_source_worlds(self):
        rows=sample()
        self.assertEqual(len(rows),100)
        for i in range(len(NAME_PAIRS)):
            group=[x for x in rows if x['entity_group']==f'entity-{i:02d}']
            self.assertEqual(len(group),len(VARIANTS))
            self.assertEqual(len({x['claim'] for x in group}),1)

    def test_explicit_meaning_and_control_conditions(self):
        supported=[make_case(0,x) for x in SUPPORT]
        self.assertTrue(all(x['supported'] for x in supported))
        contrary=make_case(0,'direct_negation')
        self.assertFalse(contrary['supported'])
        self.assertIn('does not supervise',contrary['doc'])
        unknown=make_case(0,'reverse_negation_only')
        self.assertEqual(unknown['state'],'unknown')
        self.assertIn('does not supervise',unknown['doc'])
        self.assertNotIn('identifies Aster Initiative',unknown['doc'])

    def test_reverse_negative_order_is_only_changed_order(self):
        a=make_case(0,'reverse_negation_after')['doc']
        b=make_case(0,'reverse_negation_before')['doc']
        prefix='Fictional registry; one stable period. '
        self.assertEqual(a.replace(prefix,'').split('. '),
                         list(reversed(b.replace(prefix,'').split('. '))))
        self.assertNotEqual(a,b)

    def test_paired_surface_metric_contract(self):
        rows=sample()
        predictions=[int(x['supported']) for x in rows]
        result=by_variant(rows,{'fixture_oracle':predictions},
                          {'fixture_oracle':{'unit':True}},{'verified_receipts':200})
        self.assertEqual(result['responses'],100)
        self.assertEqual(result['score_by_variant']['fixture_oracle']['active']
                         ['predicted_supported'],10)
        self.assertEqual(result['score_by_variant']['fixture_oracle']['direct_negation']
                         ['predicted_supported'],0)
        self.assertEqual(result['paired_support_surface_changes']['fixture_oracle']
                         ['reverse_negation_after']
                         ['active_support_to_other_support_switches'],0)


if __name__=='__main__':
    unittest.main()
