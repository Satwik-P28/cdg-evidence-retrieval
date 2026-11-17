import tempfile
import unittest
from pathlib import Path
from tiered_fts import Tiered, benchmark, versions


class TieredTests(unittest.TestCase):
    def test_read_exact_utf8_spans_and_queries(self):
        data=['café 😊 python package\nanother line\n'.encode(),
              b'python package\nold keyword\n',b'python package\nnew keyword\n']
        with tempfile.TemporaryDirectory() as t:
            full=Tiered(Path(t)/'full.db',data,'full')
            modes=[Tiered(Path(t)/f'{name}.db',data,name)
                   for name in ('tiered_none','tiered_column','tiered_full_nosize')]
            try:
                for engine in modes:
                    for g in range(3):
                        for query in ('python','"python package"'):
                            self.assertEqual(engine.guarded(g,query),
                                             full.lookup(g,query))
                        for rid,start,end in engine.guarded(g,'python'):
                            self.assertIn(b'python',data[g][start:end])
            finally:
                full.close()
                for m in modes:m.close()

    def test_ranked_uses_fallback_on_old_generations(self):
        docs=[b'python package\npython\n',b'python\npython package\n']
        with tempfile.TemporaryDirectory() as t:
            engine=Tiered(Path(t)/'thin.db',docs,'tiered_none')
            full=Tiered(Path(t)/'full.db',docs,'full')
            try:
                self.assertEqual(engine.guarded(0,'python',ranked=True,limit=2),
                                 full.lookup(0,'python',ranked=True,limit=2))
                self.assertEqual(engine.guarded(1,'python',ranked=True,limit=2),
                                 full.lookup(1,'python',ranked=True,limit=2))
            finally:
                engine.close();full.close()

    def test_pinned_real_history(self):
        docs=versions()
        self.assertEqual(len(docs),12)
        results=benchmark(docs)
        for row in results['results'].values():
            self.assertEqual(row['keyword_exact_parity'],120)
            self.assertEqual(row['ranked_exact_parity'],120)
            self.assertEqual(row['phrase_exact_parity'],36)

if __name__=='__main__':
    unittest.main()
