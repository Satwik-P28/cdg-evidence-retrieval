"""Round 29 local checks: search-driven source positions and reversible frames."""
import tempfile, unittest, sqlite3, os
from pathlib import Path
from retrieval_bench import make_tasks, fts_query, run_layout, eligible_lines
from filebacked_bench import build, read_spans

class FileBackedQueryTests(unittest.TestCase):
    def setUp(self):
        self.home=tempfile.TemporaryDirectory();self.addCleanup(self.home.cleanup)
        self.root=Path(self.home.name)
        self.a=self.root/'a.md';self.b=self.root/'b.md'
        self.a.write_text('# Report A\nA technical retrieval system indexes source evidence with exact original byte offsets.\nCompression-aware design permits targeted line reconstruction from independent source frames.\n',encoding='utf8')
        self.b.write_text('# Report B\nA benchmark measures query lookup latency against indexed retrieval passages and source coordinates.\nThe system uses a physically serialized index rather than oracle-supplied source spans.\n',encoding='utf8')
        self.inputs=[self.a,self.b]

    def test_source_derived_queries_have_nonempty_terms(self):
        tasks=make_tasks(self.inputs,n=6,seed=5)
        self.assertGreater(len(tasks),0)
        for t in tasks:self.assertEqual(len(t['terms']),2)

    def test_original_coordinates_are_exact_bytes(self):
        for item in eligible_lines(self.inputs):
            bs=self.inputs[item['source_id']-1].read_bytes()[item['low']:item['high']]
            self.assertEqual(bs.decode('utf8').strip(),item['text'])

    def test_fts_search_retains_source_identity(self):
        d=self.root/'whole';build(d,self.inputs,'whole',0)
        db=sqlite3.connect(d/'index.sqlite')
        hits=fts_query(db,['compression','reconstruction'],5)
        self.assertTrue(hits)
        self.assertEqual(hits[0][1],1)
        db.close()

    def test_search_to_compressed_span_roundtrip(self):
        d=self.root/'line';build(d,self.inputs,'lines',128)
        db=sqlite3.connect(d/'index.sqlite');fd=os.open(d/'frames.zst',os.O_RDONLY)
        try:
            hits=fts_query(db,['benchmark','latency'],3)
            self.assertTrue(hits)
            for _,sid,a,b,_ in hits:
                decoded,compressed,n=read_spans(db,fd,sid,[(a,b)])
                self.assertEqual(decoded[0],self.inputs[sid-1].read_bytes()[a:b]);self.assertGreater(compressed,0);self.assertGreater(n,0)
        finally:os.close(fd);db.close()

    def test_layouts_same_recall(self):
        tasks=make_tasks(self.inputs,8,42)
        one=run_layout(self.inputs,tasks,self.root/'fixed','fixed',128,warm_repeats=1)
        two=run_layout(self.inputs,tasks,self.root/'lines','lines',128,warm_repeats=1)
        self.assertEqual(one['exact_target_line_recall_at_k'],two['exact_target_line_recall_at_k'])
        self.assertEqual(one['roundtrip_errors'],0);self.assertEqual(two['roundtrip_errors'],0)

    def test_empty_span_does_not_activate_frame(self):
        d=self.root/'empty';build(d,self.inputs,'fixed',128)
        db=sqlite3.connect(d/'index.sqlite');fd=os.open(d/'frames.zst',os.O_RDONLY)
        try:
            got,bc,n=read_spans(db,fd,1,[(0,0)])
            self.assertEqual(got,[b'']);self.assertEqual(bc,0);self.assertEqual(n,0)
        finally:os.close(fd);db.close()

if __name__=='__main__':unittest.main()
