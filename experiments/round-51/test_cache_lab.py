import tempfile
import unittest
from pathlib import Path
from cache_lab import HistoricIndexCache, make_queries, bench, dependencies


class CacheTests(unittest.TestCase):
    def test_deterministic_traces(self):
        for dist in ('hot','uniform','recent'):
            self.assertEqual(make_queries(20,dist,11),make_queries(20,dist,11))

    def test_eviction_retains_exact_rank_and_phrase(self):
        r=dependencies()
        inputs=[b'python package\npython package\n',b'python test\n',
                b'package python\n',b'install uv\npython version\n']
        with tempfile.TemporaryDirectory() as t:
            full=r.Tiered(Path(t)/'full.sqlite',inputs,'full')
            thin=r.Tiered(Path(t)/'thin.sqlite',inputs,'tiered_none')
            c=HistoricIndexCache(thin,1)
            try:
                requests=[(0,'python',True),(1,'python',True),
                          (0,'"python package"',False),(2,'python',True),
                          (0,'python',True),(3,'python',True)]
                for gen,term,rank in requests:
                    actual=c.search(gen,term,rank,3 if rank else None)
                    expected=full.lookup(gen,term,rank,3 if rank else None)
                    self.assertEqual(actual,expected)
                self.assertGreater(c.misses,1)
                self.assertLessEqual(len(c.entries),1)
            finally:
                c.close();full.close();thin.close()

    def test_real_trace_all_modes(self):
        result=bench(dependencies().versions(),counts=24)
        self.assertEqual(len(result['rows']),18)
        self.assertEqual({x['distribution'] for x in result['rows']},
                         {'hot','uniform','recent'})

if __name__=='__main__':
    unittest.main()
