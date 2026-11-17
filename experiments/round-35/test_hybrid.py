import unittest
from hybrid_lab import instance,cost,exact,greedy,local,anneal,period_encode,period_decode,symmetry

class HybridTests(unittest.TestCase):
    def test_exact_consistency(self):
        for seed in range(5):
            a=instance(seed);mask,c=exact(a);self.assertEqual(cost(mask,a)[0],c)
    def test_repair_never_worsens(self):
        for seed in range(20):
            a=instance(seed);g=greedy(a);r=local(g,a);self.assertLessEqual(cost(r,a)[0],cost(g,a)[0]);self.assertEqual(cost(r,a)[1],127)
    def test_classical_anneal_returns_witness(self):
        for seed in range(10):
            a=instance(seed);self.assertEqual(cost(anneal(a,seed,100),a)[1],127)
    def test_period_reconstruction(self):
        for b in [b'',b'a',b'ab'*20,b'abcabcabc',bytes(range(251))]:self.assertEqual(period_decode(period_encode(b)),b)
    def test_reject_corruption(self):
        with self.assertRaises(ValueError):period_decode(b'P'+(5).to_bytes(4,'big')+(3).to_bytes(4,'big')+b'abc')
    def test_realism_control(self):
        s=symmetry();self.assertLess(s['periodic']['period'],s['periodic']['zlib9']);self.assertEqual(s['random']['best_method'],'raw_fallback')
if __name__=='__main__':unittest.main()
