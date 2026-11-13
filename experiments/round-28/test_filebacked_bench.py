import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
import filebacked_bench as f

class StorageTests(unittest.TestCase):
    def test_frame_losslessness_unicode(self):
        raw=('Συν + café + 🧪\nA longer second line that crosses frames\n'*7).encode()
        for layout,size in [('whole',0),('fixed',14),('lines',14),('fixed',256),('lines',256)]:
            chunks=f.chunks(raw,layout,size)
            self.assertEqual(b''.join(x for _,x in chunks),raw)
            for off,part in chunks:self.assertEqual(f.decompress(f.compress(part),len(part)),part)

    def test_exact_span_reconstruction(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);src=root/'source.txt';raw=('🐍 café\nα beta gamma\n'*5).encode();src.write_bytes(raw)
            for layout,size in [('fixed',8),('lines',8),('whole',0)]:
                out=root/layout;f.build(out,[src],layout,size)
                db=sqlite3.connect(out/'index.sqlite');fd=__import__('os').open(out/'frames.zst',__import__('os').O_RDONLY)
                try:
                    intervals=[(0,2),(1,17),(13,40),(20,20),(4,len(raw)),(0,len(raw))]
                    got,br,n=f.read_spans(db,fd,1,intervals)
                    self.assertEqual(got,[raw[a:b] for a,b in intervals]);self.assertGreater(br,0)
                finally:__import__('os').close(fd);db.close()

    def test_empty_intervals_no_read(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td);p=d/'a.txt';p.write_text('abc\n');f.build(d/'x',[p],'fixed',2)
            db=sqlite3.connect(d/'x/index.sqlite');fd=__import__('os').open(d/'x/frames.zst',__import__('os').O_RDONLY)
            try:self.assertEqual(f.read_spans(db,fd,1,[(0,0),(3,3)]),([b'',b''],0,0))
            finally:__import__('os').close(fd);db.close()

    def test_stale_version_invalidation(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td);p=d/'a.txt';p.write_text('alpha\nbeta\n')
            out=f.mutation_trial(d/'version',[p],32)
            self.assertTrue(out['stale_hash_refused']);self.assertTrue(out['replacement_hash_current'])

    def test_fts_search_real_index(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td);p=d/'a.txt';p.write_text('reversible retrieval receipts\nsecond line\n');f.build(d/'x',[p],'lines',64)
            db=sqlite3.connect(d/'x/index.sqlite');n=db.execute("SELECT count(*) FROM lines_fts WHERE lines_fts MATCH 'retrieval'").fetchone()[0];db.close()
            self.assertEqual(n,1)

    def test_seeking_across_sources(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td);p=d/'a.txt';q=d/'b.txt';p.write_bytes(b'a'*100);q.write_bytes(b'b'*180)
            f.build(d/'x',[p,q],'fixed',37)
            db=sqlite3.connect(d/'x/index.sqlite');fd=__import__('os').open(d/'x/frames.zst',__import__('os').O_RDONLY)
            try:
                self.assertEqual(f.read_spans(db,fd,1,[(10,40)])[0][0],b'a'*30)
                self.assertEqual(f.read_spans(db,fd,2,[(10,40)])[0][0],b'b'*30)
            finally:__import__('os').close(fd);db.close()

if __name__=='__main__':unittest.main()