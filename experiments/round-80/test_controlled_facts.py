import unittest
from controlled_facts import (
    generate,sha_cases,new_case,archived_docs,confusion,paired_stats,compare,
    FAMILIES,STATES,NAME_PAIRS,load,R69
)


class ControlledGroundingTests(unittest.TestCase):
    def test_complete_balanced_paired_claim_contrasts(self):
        rows=generate()
        self.assertEqual(len(rows),120)
        self.assertEqual(sum(x['supported'] for x in rows),40)
        for i in range(len(NAME_PAIRS)):
            for family in FAMILIES:
                triplet=[x for x in rows if x['entity_group']==f'entity-{i:02d}'
                         and x['family']==family]
                self.assertEqual([x['state'] for x in triplet],list(STATES))
                self.assertEqual(len({x['claim'] for x in triplet}),1)
                self.assertEqual(len({x['doc'] for x in triplet}),3)

    def test_temporal_location_role_and_two_hop_gold_contracts(self):
        for family in FAMILIES:
            s=new_case(0,family,'supported')
            c=new_case(0,family,'contradicted')
            u=new_case(0,family,'unknown')
            self.assertEqual(s['claim'],c['claim'])
            self.assertEqual(s['claim'],u['claim'])
            self.assertFalse(c['supported'])
            self.assertFalse(u['supported'])
            self.assertNotEqual(s['doc'],c['doc'])
            self.assertNotEqual(c['doc'],u['doc'])
        self.assertIn('not in Lydon',new_case(0,'location','contradicted')['doc'])
        self.assertIn('not 2018',new_case(0,'date','contradicted')['doc'])
        self.assertIn('does not supervise',new_case(0,'relation','contradicted')['doc'])
        self.assertIn('not in Lydon',new_case(0,'multihop','contradicted')['doc'])

    def test_byte_exact_source_archives(self):
        cases=generate()
        docs,report=archived_docs(cases)
        self.assertEqual(docs,[x['doc'] for x in cases])
        self.assertEqual(report['verified_receipts'],240)
        self.assertGreater(report['archive_persistent_bytes']['whole'],0)
        self.assertGreater(report['archive_persistent_bytes']['gear512'],0)
        self.assertEqual(len(sha_cases(cases)),64)

    def test_confusion_is_binary_support_not_hallucination_warning(self):
        rows=generate()
        gold=[int(x['supported']) for x in rows]
        perfect=confusion(gold,rows)
        self.assertEqual((perfect['tp'],perfect['tn'],perfect['fp'],perfect['fn']),
                         (40,80,0,0))
        self.assertEqual(perfect['balanced_accuracy'],1)
        reject_all=confusion([0]*len(rows),rows)
        self.assertEqual(reject_all['balanced_accuracy'],.5)
        self.assertEqual(reject_all['supported_recall'],0)

    def test_multi_condition_triads_and_state_stratification(self):
        rows=generate()
        gold=[int(x['supported']) for x in rows]
        values=paired_stats(rows,gold)
        self.assertEqual(values['all']['states']['unknown']['accepted'],0)
        self.assertEqual(values['location']['states']['supported']['n'],10)
        out=compare(rows,{'oracle_fixture':gold},
                    {'oracle_fixture':{'test_only':True}},{'verified_receipts':240})
        self.assertEqual(out['matched_triples']['oracle_fixture']
                         ['fully_correct_support_contradiction_unknown_triples'],40)
        self.assertEqual(sum(out['state_counts'].values()),120)


if __name__=='__main__':
    unittest.main()
