import unittest,random
from benchmark import make_case,select,run
class TestR37(unittest.TestCase):
 def test_reproducible(self):self.assertEqual(run(25),run(25))
 def test_budget(self):
  c=make_case(2,random.Random(12));self.assertTrue(all(len(select(c,p)['selected'])<=3 for p in ('fixed','iterative','version_filtered','title_version','adaptive')))
 def test_known_gold_only_for_score(self):
  c=make_case(4,random.Random(2));a=select(c,'fixed');c['gold']={'unreachable'};b=select(c,'fixed');self.assertEqual(a['selected'],b['selected']);self.assertNotEqual(a['complete'],b['complete'])
 def test_source_receipts_present(self):
  c=make_case(3,random.Random(3));z=select(c,'adaptive');self.assertEqual(len(z['source_hashes']),len(z['selected']))
 def test_shift_repeatable(self):
  c=make_case(3,random.Random(3),True);self.assertEqual(select(c,'iterative'),select(c,'iterative'))
 def test_baseline_dominates_adaptive_on_metadata_fixture(self):
  for shift in (False,True):
   for i in range(20):
    c=make_case(i,random.Random(i),shift)
    a=select(c,'adaptive');b=select(c,'title_version')
    self.assertEqual(a['selected'],b['selected'])
    self.assertGreater(a['total_cost'],b['total_cost'])
 def test_false_accept_consistency(self):
  for p in ('fixed','iterative','version_filtered','title_version','adaptive'):
   z=select(make_case(7,random.Random(8),True),p);self.assertEqual(z['false_accept'],z['accepted'] and not z['complete'])
if __name__=='__main__':unittest.main()
