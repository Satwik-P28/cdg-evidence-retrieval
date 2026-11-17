import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from evidence_bridge import EvidenceFTS,VersionedReader,Receipt,experiment,dynamic,OLD


class TestEvidenceBridge(unittest.TestCase):
    def test_index_spans_are_utf8_bytes_and_generation_specific(self):
        versions=['café 😊 evidence\nnew detail\n'.encode(),
                  'café 😊 corrected\nnew detail\n'.encode()]
        with tempfile.TemporaryDirectory() as home:
            idx=EvidenceFTS(versions,Path(home)/'history.sqlite')
            before=idx.query(0,'evidence')
            after=idx.query(1,'evidence')
            self.assertEqual(len(before),1)
            self.assertEqual(len(after),0)
            start,end=before[0]
            self.assertEqual(versions[0][start:end],'café 😊 evidence\n'.encode())
            idx.close()

    def test_exact_receipt_and_stale_rejection(self):
        data=[b'alpha evidence\n',b'alpha revised\n']
        store=VersionedReader(data,'gear512','binary-zlib')
        receipt=store.receipt(0,0,5)
        with self.assertRaises(ValueError):
            store.read(receipt)
        self.assertEqual(store.read(receipt,pin_generation=0)[0],b'alpha')
        tampered=replace(receipt,source_sha256='0'*64)
        with self.assertRaises(ValueError):
            store.read(tampered,pin_generation=0)
        bad=replace(receipt,manifest_sha256='0'*64)
        with self.assertRaises(ValueError):
            store.read(bad,pin_generation=0)

    def test_metadata_and_payload_corruption_rejected(self):
        store=VersionedReader([b'evidence one\n'],'fixed512','json-zlib')
        receipt=store.receipt(0,0,8)
        stored=bytearray(store.packed_manifest);stored[-1]^=2
        store.packed_manifest=bytes(stored)
        with self.assertRaises(ValueError):
            store.read(receipt,pin_generation=0)
        store=VersionedReader([b'evidence two\n'],'fixed512','binary-zlib')
        receipt=store.receipt(0,0,8)
        key=next(iter(store.archive.frames))
        store.archive.frames[key]=b'not zlib'
        with self.assertRaises(Exception):
            store.read(receipt,pin_generation=0)

    def test_integrated_authentic_versions(self):
        versions=dynamic('cdg_r46_for_test48',OLD).load_source()
        data=experiment(versions)
        self.assertEqual(data['versions'],12)
        self.assertEqual(len(data['methods']),5)
        self.assertGreater(data['retrieved_evidence_spans'],50)
        self.assertGreater(data['persistent_fts_index_bytes'],0)

if __name__=='__main__':
    unittest.main()
