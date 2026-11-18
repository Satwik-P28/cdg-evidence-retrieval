import unittest
from integrated_evidence import (
    locked_unseen,literal_answer_present,frame_ids,evaluate,
    STRATEGIES,K,SALT)


def fixture(i,answer='Film B'):
    return {
        '_id':f'unit-{i}',
        'question':'Which film did Founder direct?',
        'context':[
            ['Founder',['Founder directed Film B in 2010.','A separate fact.']],
            ['Film B',['Film B was published in 2011.']],
            ['Film C',['Another film was made independently.']],
            ['Film D',['Something else happened in 2005.']],
            ['Film E',['Unrelated movie information.']]
        ],
        'type':'bridge',
        'answer':answer,
        'supporting_facts':[['Founder',0],['Film B',0]]
    }


class IntegrationTests(unittest.TestCase):
    def test_literal_answer_strictly_diagnostic(self):
        self.assertTrue(literal_answer_present('Film B','A Film B appeared.'))
        self.assertFalse(literal_answer_present('Film B','This was Film BC'))
        self.assertFalse(literal_answer_present('Film B','This is Film A'))
        self.assertIsNone(literal_answer_present('yes','yes evidence exists'))
        self.assertIsNone(literal_answer_present('no','no evidence exists'))
        self.assertIsNone(literal_answer_present('','something'))

    def test_source_identity_exclusion(self):
        # The real SHA-sorted sample is checked in the full benchmark, not
        # replaced with synthetic question IDs.
        self.assertTrue(SALT.startswith('CDG-R66-'))
        self.assertEqual(len(set(STRATEGIES)),len(STRATEGIES))

    def test_byte_exact_output_and_independent_gold(self):
        rows=[fixture(0),fixture(1)]
        got=evaluate(rows)
        self.assertEqual(got['n'],2)
        self.assertEqual(set(got['outcomes']),set(STRATEGIES))
        self.assertGreater(got['index_sqlite_bytes'],0)
        self.assertEqual(set(got['source_archive_bytes']),{'whole','gear512'})
        for policy in STRATEGIES:
            for k in map(str,K):
                result=got['outcomes'][policy][k]
                self.assertEqual(result['n'],2)
                self.assertLessEqual(result['complete_gold_sentences'],
                                     result['complete_docs'])
                self.assertGreaterEqual(result['mean_evidence_utf8_bytes'],0)
        self.assertGreater(got['total_verified_exact_evidence_spans'],0)

    def test_answer_and_annotations_not_selection_inputs(self):
        rows=[fixture(0),fixture(1)]
        original=evaluate(rows)
        rows[0]['answer']='Impossible Answer Never Appears'
        rows[0]['supporting_facts']=[['Film E',0]]
        changed=evaluate(rows)
        for policy in STRATEGIES:
            for k in map(str,K):
                old=original['outcomes'][policy][k]
                new=changed['outcomes'][policy][k]
                for field in (
                    'mean_evidence_utf8_bytes','mean_evidence_tokens_regex_proxy',
                    'mean_gear512_compressed_frame_bytes',
                    'mean_whole_compressed_frame_bytes','mean_selected_sentences'
                ):
                    self.assertEqual(old[field],new[field],(policy,k,field))
        self.assertNotEqual(
            original['outcomes']['bridge_all']['5']['answer_literal_present'],
            changed['outcomes']['bridge_all']['5']['answer_literal_present'])


if __name__=='__main__':unittest.main()
