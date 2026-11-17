import tempfile,unittest
from pathlib import Path
from lab import Global,GlobalDelta,Shards,Hybrid,exercise,source_docs
class TestStorage(unittest.TestCase):
 def test_equal_content_independent_names(self):
  with tempfile.TemporaryDirectory() as t:
   docs={'alpha':b'evidence source\n','beta':b'evidence source\n'}
   engines=[C(Path(t)/str(i),docs) for i,C in enumerate([Global,GlobalDelta,Shards,Hybrid])]
   for e in engines:
    self.assertEqual(sorted(name for name,_ in e.search('evidence')),['alpha','beta'])
    self.assertEqual(e.read_gen(0,'alpha'),docs['alpha'])
    self.assertEqual(e.read_gen(0,'beta'),docs['beta'])
    e.close()
 def test_rename_and_remove_retains_history(self):
  with tempfile.TemporaryDirectory() as t:
   docs={'old':b'frame evidence\n','keep':b'other evidence\n'}
   engines=[C(Path(t)/str(i),docs) for i,C in enumerate([Global,GlobalDelta,Shards,Hybrid])]
   new={'new':docs['old'],'keep':docs['keep']}
   for e in engines:
    e.update(new)
    self.assertEqual(sorted(name for name,_ in e.search('frame')),['new'])
    self.assertEqual(e.read_gen(0,'old'),docs['old'])
    self.assertEqual(e.read_gen(1,'new'),docs['old'])
    e.close()
 def test_middle_line_replacement(self):
  with tempfile.TemporaryDirectory() as t:
   engines=[C(Path(t)/str(i),{'x':b'alpha evidence\nbeta proof\n'}) for i,C in enumerate([Global,GlobalDelta,Shards,Hybrid])]
   for e in engines:
    e.update({'x':b'alpha evidence\ngamma proof\n'})
    self.assertEqual(len(e.search('beta')),0)
    self.assertEqual(len(e.search('gamma')),1)
    self.assertEqual(e.read_gen(0,'x'),b'alpha evidence\nbeta proof\n')
    e.close()
 def test_repeated_report_run(self):
  r=exercise(5,.2,11,updates=2)
  self.assertGreater(r['final_global_bytes'],0)
  self.assertGreater(r['final_delta_bytes'],0)
  self.assertGreater(r['final_shards_bytes'],0)
  self.assertGreater(r['final_hybrid_bytes'],0)
if __name__=='__main__':unittest.main()
