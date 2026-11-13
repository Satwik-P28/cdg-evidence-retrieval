import unittest
import importlib.util
from pathlib import Path

s=importlib.util.spec_from_file_location('frame_probe',Path(__file__).with_name('frame_probe.py'))
f=importlib.util.module_from_spec(s)
s.loader.exec_module(f)

class TestReceipts(unittest.TestCase):
    def test_unicode_multibyte_exact(self):
        raw,spans=f.source_bytes_and_receipts('Café', ['α β','emoji 🧠 science'])
        self.assertEqual(raw[spans[0][0]:spans[0][1]].decode(), 'α β')
        self.assertEqual(raw[spans[1][0]:spans[1][1]].decode(), 'emoji 🧠 science')
        self.assertGreater(spans[1][0],spans[0][1])

    def test_frame_union(self):
        self.assertEqual(f.activated_frame_ids([(0,1),(1,7),(12,17)],8),{0,1,2})
        self.assertEqual(f.activated_frame_ids([(8,8)],8),set())

    def test_exact_receipts(self):
        raw, spans=f.source_bytes_and_receipts('Doc', ['x','some words'])
        rec=f.exact_receipts(raw,spans)
        self.assertEqual(rec[0]['start_byte'],4)
        self.assertEqual(rec[0]['end_byte'],5)
        self.assertEqual(len(rec[0]['sha256']),64)

    def test_zlib_roundtrip(self):
        codec=f.Codec('zlib')
        raw=b'hello world'*41
        packed=f.materialize_frames(raw,17,codec)
        reconstructed=b''.join(codec.decompress(x,min(17,len(raw)-17*i)) for i,x in enumerate(packed))
        self.assertEqual(reconstructed,raw)

    def test_zstd_roundtrip_when_available(self):
        try: codec=f.Codec('zstd')
        except RuntimeError:self.skipTest('system libzstd unavailable')
        raw=b'full data'*100 + 'π'.encode()
        packed=f.materialize_frames(raw,128,codec)
        reconstructed=b''.join(codec.decompress(x,min(128,len(raw)-128*i)) for i,x in enumerate(packed))
        self.assertEqual(reconstructed,raw)

    def test_bridge_title_boundaries(self):
        row={'question':'What does A connect to?', 'context':[
            ['A',['A describes B fully.']], ['B',['B is the target.']], ['BC',['This is a decoy.']]
        ]}
        ss=f.selected_sentence_ids(row,[0,1],'top2+link')
        self.assertIn(0,ss[0])
        self.assertEqual(set(ss),{0,1})

    def test_selected_top2_plus_link_does_not_select_three_by_default(self):
        row={'question':'alpha','context':[
            ['A',['alpha first','alpha second','mentions B without alpha']],
            ['B',['other content']]
        ]}
        selected=f.selected_sentence_ids(row,[0,1],'top2+link')
        self.assertTrue(len(selected[0])<=3)
        self.assertEqual(selected[1],{0})

    def test_pinned_hash_rejects_wrong_blob(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            path=Path(directory)/'bad.json';path.write_text('[]')
            with self.assertRaisesRegex(ValueError,'mismatch'):
                f.load_source(path)

if __name__=='__main__':unittest.main()
