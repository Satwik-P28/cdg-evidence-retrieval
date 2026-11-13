"""Round 27 correctness tests only; not evidence of representative performance."""
import tempfile,unittest
from pathlib import Path
from storage_bench import Zstd,lines,fixed,line_aligned,activation,record_one,run

class FrameTests(unittest.TestCase):
    def setUp(self):
        self.raw=("Heading: café 漢字🙂\n"+"The evidence sentence about graph retrieval is here.\n"+"A short line.\n"+"A very long sentence "*40+"\n").encode('utf-8')
        self.codec=Zstd()
    def test_frame_cover(self):
        for b in (32,64,128,256,1024):
            for fn in (fixed,line_aligned):
                xs=fn(self.raw,b) if fn==fixed else fn(self.raw,None,b)
                self.assertEqual(b''.join(self.raw[a:c] for a,c in xs),self.raw)
                self.assertTrue(all(0<c-a<=b for a,c in xs))
    def test_roundtrip_all_frames(self):
        for b in (32,128,512):
            frame=fixed(self.raw,b)
            packed,selected,_=record_one(self.raw,[(0,17),(30,60)],frame,self.codec)
            self.assertGreater(len(packed),0)
            self.assertEqual(selected,activation(frame,[(0,17),(30,60)]))
    def test_multibyte_offsets(self):
        pos=self.raw.find('漢字🙂'.encode())
        self.assertGreater(pos,0)
        spans=[(pos,pos+len('漢字🙂'.encode()))]
        for b in (16,128,512):
            record_one(self.raw,spans,line_aligned(self.raw,None,b),self.codec)
    def test_empty_spans(self):
        self.assertEqual(activation(fixed(self.raw,32),[]),[])
        self.assertEqual(activation(fixed(self.raw,32),[(10,10)]),[])
    def test_exact_line_grid(self):
        self.assertGreaterEqual(lines(self.raw)[0][0],0)
        self.assertGreaterEqual(len(lines(self.raw)),2)
    def test_both_workloads(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'test.txt'
            p.write_bytes((self.raw*25))
            a=run([p],queries=12,span_style='whole_line')
            b=run([p],queries=12,span_style='subspan')
            self.assertEqual(a['workload']['queries'],12)
            self.assertEqual(b['workload']['span_style'],'subspan')
            self.assertLess(b['workload']['mean_requested_source_bytes'],a['workload']['mean_requested_source_bytes'])
    def test_deterministic_counts(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'test.txt';p.write_bytes(self.raw*25)
            a=run([p],queries=8,seed=8)
            b=run([p],queries=8,seed=8)
            for key in a['layouts']:
                self.assertEqual(a['layouts'][key]['mean_compressed_read_bytes'],b['layouts'][key]['mean_compressed_read_bytes'])

if __name__=='__main__':unittest.main()