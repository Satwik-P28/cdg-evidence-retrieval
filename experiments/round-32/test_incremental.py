import tempfile, unittest
from pathlib import Path
from incremental_store import Store, chunks
from benchmark import update

class TestStore(unittest.TestCase):
    def test_utf8_reconstruction_and_exact_coordinates(self):
        with tempfile.TemporaryDirectory() as td:
            x='café 🦊\nsecond line\n'.encode()
            s=Store(Path(td),frame_size=32);s.publish({'one':x})
            r=s.reader();self.assertEqual(r.read(r.receipt('one',0,len(x))),x)
            self.assertEqual(r.read(r.receipt('one',3,9)),x[3:9])
    def test_old_reader_pinned_and_reject_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            s=Store(Path(td));s.publish({'one':b'first evidence\n'})
            old=s.reader();a=old.receipt('one',0,5)
            s.publish({'one':b'newer evidence\n'})
            self.assertEqual(old.read(a),b'first')
            with self.assertRaises(ValueError):s.reader().read(a)
    def test_cas_deduplicates_unchanged_frames(self):
        with tempfile.TemporaryDirectory() as td:
            s=Store(Path(td),frame_size=512)
            x={'one':b'one evidence\nmore\n','two':b'two evidence\nmore\n'}
            s.publish(x);old=list((Path(td)/'frames').glob('*.zst'))
            x['one']=b'one evidence\nNEW\n';s.publish(x)
            latest=list((Path(td)/'frames').glob('*.zst'))
            self.assertLess(len(latest),2*len(old))
    def test_failed_publication_preserves_current(self):
        with tempfile.TemporaryDirectory() as td:
            s=Store(Path(td));g=s.publish({'one':b'a\n'})['generation']
            with self.assertRaises(RuntimeError):s.publish({'one':b'b\n'},fail_before_pointer=True)
            self.assertEqual(s.reader().manifest['generation'],g)
    def test_corruption_detected(self):
        with tempfile.TemporaryDirectory() as td:
            s=Store(Path(td));p=s.publish({'one':b'evidence\n'})
            f=Path(td)/s.reader().manifest['sources']['one']['frames'][0]['path']
            f.write_bytes(b'corrupt')
            with self.assertRaises(ValueError):s.reader()
    def test_descriptor_corruption_detected(self):
        with tempfile.TemporaryDirectory() as td:
            s=Store(Path(td));p=s.publish({'one':b'evidence\n'})
            desc=Path(td)/p['manifest']['sources']['one']['descriptor']
            desc.write_bytes(b'{}')
            with self.assertRaises(ValueError):s.reader()
    def test_monolithic_vs_cas_search_parity(self):
        with tempfile.TemporaryDirectory() as td:
            a=Store(Path(td)/'a',full_rebuild=True)
            b=Store(Path(td)/'b',full_rebuild=False)
            docs={'one':b'evidence in a source\n','two':b'source needs evidence\n'}
            a.publish(docs);b.publish(docs)
            self.assertEqual([(r['receipt']['name'],r['text']) for r in a.reader().search('evidence')],[(r['receipt']['name'],r['text']) for r in b.reader().search('evidence')])
    def test_update_kinds(self):
        x=b'This is evidence.\n';self.assertEqual(len(update(x,1,'replace')),len(x));self.assertEqual(len(update(x,1,'insert')),len(x)+1)
    def test_bad_ranges(self):
        with tempfile.TemporaryDirectory() as td:
            s=Store(Path(td));s.publish({'one':b'ab'})
            with self.assertRaises(ValueError):s.reader().receipt('one',1,10)

if __name__=='__main__':unittest.main()
