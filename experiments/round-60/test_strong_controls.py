import tempfile
import unittest
import zlib
from strong_controls import Archive,CONTROLS,git_pack_control,load,R46,R47,codec_api


class StrongControlsTests(unittest.TestCase):
    def setUp(self):
        self.chunker=load('cdg46_strong_control_unit',R46)
        self.manifest=load('cdg47_strong_control_unit',R47)
        self.history=[
            ('history',b'original version of a readme\n'*50),
            ('history',b'original version of a readme\n'*47+b'new lines\n'*3),
        ]
        self.independent=[
            ('independent',b'Caf\xc3\xa9 UTF-8 source one\n'),
            ('independent',b'Another independent source without repeated content\n'),
        ]

    def test_codec_exact_readback_and_spans(self):
        data=self.history+self.independent
        for name,method,codec in CONTROLS:
            store=Archive(data,method,codec,self.chunker.frame,self.manifest)
            self.assertGreater(store.size(),0,name)
            self.assertEqual(len(store.method_choices),len(data))
            for i,(_,blob) in enumerate(data):
                self.assertEqual(store.read(i,0,len(blob))[0],blob,name)
                self.assertEqual(store.read(i,1,min(len(blob),40))[0],
                                 blob[1:min(len(blob),40)],name)
                with self.assertRaises(ValueError):
                    store.read(i,-1,2)

    def test_corruption_rejected(self):
        data=self.history
        for _,method,codec in CONTROLS:
            store=Archive(data,method,codec,self.chunker.frame,self.manifest)
            key=next(iter(store.frames))
            store.frames[key]=b'not a compressed frame'
            with self.assertRaises(Exception):
                store.read(0,0,len(data[0][1]))

    def test_zstd_real_codec_and_mode(self):
        for codec in ('zstd3','zstd9','zlib6'):
            encode,decode=codec_api(codec)
            raw=(b'lossless bytes for codec check\xc3\xa9\n'*300)
            self.assertEqual(decode(encode(raw)),raw)
        store=Archive(self.history+self.independent,'cohort','zstd3',
                      self.chunker.frame,self.manifest)
        self.assertEqual(store.method_choices,
                         ['gear512','gear512','whole','whole'])

    def test_git_pack_control_real_revisions(self):
        result=git_pack_control(self.history,self.independent)
        self.assertTrue(result['readback_verified'])
        self.assertGreater(result['pack_bytes'],0)
        self.assertGreater(result['pack_index_bytes'],0)
        self.assertGreater(result['entire_git_metadata_bytes'],0)
        self.assertEqual(result['commits'],3)

    def test_same_span_sampling_is_deterministic(self):
        data=self.history+self.independent
        first=Archive(data,'whole','zstd3',self.chunker.frame,self.manifest)
        second=Archive(data,'whole','zstd3',self.chunker.frame,self.manifest)
        self.assertEqual(first.evaluate()['mean_compressed_span_traffic'],
                         second.evaluate()['mean_compressed_span_traffic'])


if __name__=='__main__':
    unittest.main()
