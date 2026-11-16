import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('selection_lab',Path(__file__).with_name('selection_lab.py'))
mod=importlib.util.module_from_spec(spec)
import sys
sys.modules['selection_lab']=mod
spec.loader.exec_module(mod)
Candidate=mod.Candidate;Problem=mod.Problem

class Tests(unittest.TestCase):
    def test_shared_frame_only_once(self):
        p=Problem(frozenset([0,1]),(Candidate(frozenset([0]),frozenset([0]),2),Candidate(frozenset([1]),frozenset([0]),2)),(10,),.5)
        self.assertEqual(mod.cost(p,[0,1]),12)
    def test_exact_optimum(self):
        p=Problem(frozenset([0,1]),(Candidate(frozenset([0]),frozenset([0]),1),Candidate(frozenset([1]),frozenset([1]),1),Candidate(frozenset([0,1]),frozenset([2]),1)),(10,10,5),1)
        self.assertEqual(mod.exact(p),(2,))
    def test_unanswerable(self):
        p=Problem(frozenset([0,1]),(Candidate(frozenset([0]),frozenset([0]),1),),(10,),1)
        self.assertIsNone(mod.exact(p));self.assertIsNone(mod.greedy(p))
    def test_ratio_never_suboptimal_exact(self):
        for seed in range(14):
            p=mod.make_problem(seed,'bridge',n=9)
            g=mod.greedy(p);o=mod.exact(p)
            self.assertEqual(mod.covered(p,g),p.required)
            self.assertLessEqual(mod.cost(p,o),mod.cost(p,g)+1e-8)
    def test_deterministic(self):self.assertEqual(mod.run(2,3),mod.run(2,3))
if __name__=='__main__':unittest.main()
