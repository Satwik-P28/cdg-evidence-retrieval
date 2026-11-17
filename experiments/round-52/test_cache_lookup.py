import unittest
from cache_lookup import bench,load


class CacheLookupTests(unittest.TestCase):
    def test_span_strategy_regression(self):
        out=bench(count=18)
        self.assertEqual(out['version_count'],12)
        self.assertEqual(len(out['rows']),3*4*3)
        for row in out['rows']:
            self.assertEqual(row['queries'],18)
            self.assertGreaterEqual(row['cache_hits'],0)
            self.assertGreaterEqual(row['cache_misses'],0)

    def test_point_batch_return_same_order_and_duplicates(self):
        old=load()
        docs=[b'python package\npython package\n',b'package python\n',b'evidence\n']
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as t:
            engine=old.dependencies().Tiered(Path(t)/'thin.db',docs,'tiered_none')
            try:
                outcomes=[]
                for method in ('scan','point','batch'):
                    cache=old.HistoricIndexCache(engine,2,method)
                    try:
                        outcomes.append(cache.search(0,'python',True,3))
                        self.assertEqual(cache.search(0,'"python package"',False),
                                         cache.search(0,'"python package"',False))
                    finally:
                        cache.close()
                self.assertEqual(outcomes[0],outcomes[1])
                self.assertEqual(outcomes[1],outcomes[2])
            finally:
                engine.close()

if __name__=='__main__':
    unittest.main()
