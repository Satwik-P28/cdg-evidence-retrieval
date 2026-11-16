"""Round 34 deterministic local checks. Run with unittest discover in this folder."""
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from planner_lab import prune,repair,predicted_problem,acquire_with_observation,benchmark
_here = Path(__file__).resolve().parent
_round33 = next((p for p in (_here.parent/'round-33', _here.parent/'cdg_round33') if (p/'selection_lab.py').exists()), None)
if _round33 is None: raise RuntimeError('Round 33 selection_lab.py is required')
sys.path.insert(0,str(_round33))
from selection_lab import make_problem,exact,greedy,cost,covered

class TestPlanner(unittest.TestCase):
    def test_repair_feasible_and_not_more_expensive(self):
        for fam in ('independent','shared','bridge'):
            for seed in range(20):
                p=make_problem(seed+500,fam);g=greedy(p)
                selection,evaluated=repair(p,g)
                self.assertTrue(p.required<=covered(p,selection))
                self.assertLessEqual(cost(p,selection),cost(p,g)+1e-8)
                self.assertGreater(evaluated,0)
    def test_optimal_bound(self):
        for fam in ('independent','shared','bridge'):
            p=make_problem(731,fam)
            self.assertGreaterEqual(cost(p,repair(p,greedy(p))[0]),cost(p,exact(p))-1e-8)
    def test_prune_does_not_raise_cost(self):
        p=make_problem(600,'bridge');g=greedy(p);x=prune(p,g)
        self.assertLessEqual(cost(p,x),cost(p,g)+1e-8)
        self.assertTrue(p.required<=covered(p,x))
    def test_prediction_is_not_actual_evidence(self):
        p=make_problem(43,'shared');noisy=predicted_problem(p,3,.5)
        self.assertNotEqual([c.covers for c in p.candidates],[c.covers for c in noisy.candidates])
        self.assertEqual([c.frames for c in p.candidates],[c.frames for c in noisy.candidates])
    def test_observation_only_sees_selected_true_facets(self):
        for fam in ('independent','shared','bridge'):
            p=make_problem(33116,fam)
            for corruption in (0,.05,.3,1.0):
                pred=predicted_problem(p,42,corruption)
                acquired,ok=acquire_with_observation(p,pred)
                self.assertTrue(ok)
                self.assertTrue(p.required<=covered(p,acquired))
    def test_small_benchmark(self):
        x=benchmark(3)
        self.assertEqual(x['methods']['exact']['exact_matches'],9)
        self.assertEqual(x['noise_stress']['0']['observed_acquisition']['complete'],9)

if __name__=='__main__':unittest.main()
