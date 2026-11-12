"""Regression tests for the deliberately limited Round 23 controlled fixture."""
import unittest
from cdg_round23_lab import (CASES_PER_MODE, MODES, attempt, make_case,
                             parse_subject, parse_route, receipt_checks, run)

class TestRound23(unittest.TestCase):
    def test_exact_subject(self):
        self.assertEqual(parse_subject('Entry subject25 connects to route route25.'), 'subject25')
        self.assertNotEqual(parse_subject('Entry subject250 connects to route route250.'), 'subject25')

    def test_exact_route(self):
        self.assertEqual(parse_route('Entry a connects to route route25.'), 'route25')

    def test_guarded_cases(self):
        expected={
            'clean':'result111',
            'conflicting_anchors':None,
            'stale_version':'result111',
            'scope_collision':'result111',
            'missing_second_hop':None,
        }
        for mode, answer in expected.items():
            with self.subTest(mode=mode):
                c=make_case(111,mode)
                self.assertEqual(attempt(c,'guarded')[0],answer)

    def test_unsafe_policy_fails_injections(self):
        for mode in ('conflicting_anchors','stale_version','scope_collision'):
            with self.subTest(mode=mode):
                c=make_case(111,mode)
                self.assertNotEqual(attempt(c,'naive')[0],c['expected'])

    def test_receipts(self):
        self.assertTrue(all(receipt_checks().values()))

    def test_reproducibility_counts(self):
        result=run()
        self.assertEqual(set(result['results']),set(MODES))
        for mode in MODES:
            for p in ('static','naive','guarded'):
                self.assertEqual(result['results'][mode][p]['total_cases'],CASES_PER_MODE)

if __name__=='__main__':
    unittest.main()
