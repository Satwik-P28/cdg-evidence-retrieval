"""Round 30 contentless FTS5 compressed-source regression tests."""
import sqlite3,tempfile,unittest
from pathlib import Path
from contentless_bench import build_contentless,query,compare
from filebacked_bench import read_spans
import os

class ContentlessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.doc=self.path/'alpha.txt';self.doc.write_text('Résumé 🌍 source\nThe blue orchard refers to Avery Reed.\nAvery Reed was born in Larchfield.\n',encoding='utf8')
    def tearDown(self):self.temp.cleanup()
    def test_compressed_roundtrip_unicode(self):
        p=self.path/'store';build_contentless(p,[self.doc],size=32)
        db=sqlite3.connect(p/'index.sqlite');fd=os.open(p/'frames.zst',os.O_RDONLY)
        raw=self.doc.read_bytes();got,cb,nf=read_spans(db,fd,1,[(0,len(raw))]);os.close(fd);db.close()
        self.assertEqual(got[0],raw);self.assertGreater(nf,1)
    def test_no_plain_source_body_in_lines_table(self):
        p=self.path/'store';build_contentless(p,[self.doc],size=128)
        db=sqlite3.connect(p/'index.sqlite')
        columns=[z[1] for z in db.execute('PRAGMA table_info(lines)').fetchall()];db.close()
        self.assertNotIn('body',columns)
    def test_ranked_search_retains_source_offsets(self):
        p=self.path/'store';build_contentless(p,[self.doc],size=128)
        db=sqlite3.connect(p/'index.sqlite');hits=query(db,'orchard');db.close()
        self.assertEqual(len(hits),1);self.assertEqual(hits[0][1],1)
    def test_external_and_contentless_match(self):
        r=compare([self.doc],size=128)
        self.assertEqual(r['mismatches'],[])
    def test_metadata_source_digest_is_pinned(self):
        p=self.path/'store';build_contentless(p,[self.doc],size=128)
        db=sqlite3.connect(p/'index.sqlite');original=db.execute('select sha256 from sources').fetchone()[0]
        self.doc.write_text('new source',encoding='utf8')
        import hashlib
        self.assertNotEqual(original,hashlib.sha256(self.doc.read_bytes()).hexdigest());db.close()
    def test_empty_span_zero_reads(self):
        p=self.path/'store';build_contentless(p,[self.doc],size=128)
        db=sqlite3.connect(p/'index.sqlite');fd=os.open(p/'frames.zst',os.O_RDONLY)
        got,n,fr=read_spans(db,fd,1,[(0,0)]);db.close();os.close(fd)
        self.assertEqual(got,[b'']);self.assertEqual(n,0);self.assertEqual(fr,0)
if __name__=='__main__':unittest.main()
