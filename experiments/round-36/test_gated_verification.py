import unittest
from gated_verification import instances,evaluate,simulate,choose_threshold
import random

class Check(unittest.TestCase):
    def test_reproducible(self):
        self.assertEqual(simulate(),simulate())
    def test_no_leakage(self):
        d=simulate();self.assertGreater(d['test_n'],100)
        self.assertNotIn('answer',d)
    def test_screen_never_uses_more_deep_calls(self):
        rows=instances(200,random.Random(1))
        a=evaluate(rows,.8,.5)
        self.assertLessEqual(a['screen_then_deep']['deep_verifications'],a['deep_all']['deep_verifications'])
    def test_screen_cannot_add_accepts(self):
        rows=instances(200,random.Random(2))
        a=evaluate(rows,.8,.5)
        self.assertLessEqual(a['screen_then_deep']['accepted'],a['deep_all']['accepted'])
    def test_extreme_threshold(self):
        rows=instances(200,random.Random(3))
        a=evaluate(rows,1.01,.5)
        self.assertEqual(a['deep_all']['accepted'],0)
    def test_stricter_gate_reduces_verification(self):
        rows=instances(300,random.Random(4))
        a=evaluate(rows,.8,.35);b=evaluate(rows,.8,.65)
        self.assertGreaterEqual(a['screen_then_deep']['deep_verifications'],b['screen_then_deep']['deep_verifications'])
if __name__=='__main__':unittest.main()
