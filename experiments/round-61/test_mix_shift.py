import unittest
from mix_shift import experiment,POLICIES,HISTORY_COUNTS,INDEPENDENT_COUNTS


class MixShiftTests(unittest.TestCase):
    def test_same_source_multiset_at_every_policy(self):
        history=[('history',(b'stable source\n'*40)+b'revision 1'),
                 ('history',(b'stable source\n'*40)+b'revision 2')]
        sources=[('independent',f'independent source {i}\n'.encode()) for i in range(1030)]
        # Exercise a reduced synthetic fixture via monkeypatched regime counts
        import mix_shift
        old_h,old_i=mix_shift.HISTORY_COUNTS,mix_shift.INDEPENDENT_COUNTS
        mix_shift.HISTORY_COUNTS=(0,2)
        mix_shift.INDEPENDENT_COUNTS=(96,)
        try:
            result=experiment(history,sources,'synthetic')
        finally:
            mix_shift.HISTORY_COUNTS,mix_shift.INDEPENDENT_COUNTS=old_h,old_i
        self.assertEqual(len(result['scenarios']),2)
        for scenario in result['scenarios']:
            self.assertEqual(set(scenario['policies']),set(POLICIES))
            baseline=scenario['policies']['all_whole']
            self.assertEqual(baseline['archive_delta_pct_vs_whole'],0)
            for method in POLICIES:
                self.assertEqual(scenario['policies'][method]['span_queries'],
                                 2*(scenario['history_count']+scenario['independent_count']))
                self.assertGreater(scenario['policies'][method]['archive_bytes'],0)
        self.assertEqual(len(result['online_read_weighted_vs_whole']),2)

    def test_frozen_regime_list(self):
        self.assertEqual(HISTORY_COUNTS,(0,3,6,12))
        self.assertEqual(INDEPENDENT_COUNTS,(96,384,1024))


if __name__=='__main__':
    unittest.main()
