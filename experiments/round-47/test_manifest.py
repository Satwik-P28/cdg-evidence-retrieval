import unittest
from manifest_lab import enc_int,dec_int,pack_binary,unpack_binary,encode,decode,FORMATS,measure,prior


class TestManifestPacking(unittest.TestCase):
    def test_unsigned_integer_roundtrip(self):
        for i in (0,1,127,128,255,256,1024,2**32,2**63-1):
            b=enc_int(i)
            got,end=dec_int(b,0)
            self.assertEqual(got,i)
            self.assertEqual(end,len(b))
        with self.assertRaises(ValueError):
            enc_int(-1)
        with self.assertRaises(ValueError):
            dec_int(bytes([128]),0)

    def test_roundtrip_all_encodings(self):
        entries=[
          {'sha':'f'*64,'size':256,
           'frames':[{'sha':'a'*64,'len':50},{'sha':'b'*64,'len':206}]},
          {'sha':'e'*64,'size':50,
           'frames':[{'sha':'a'*64,'len':50}]},
          {'sha':'d'*64,'size':0,'frames':[{'sha':'c'*64,'len':0}]}]
        for mode in FORMATS:
            packed=encode(entries,mode)
            self.assertEqual(decode(packed,mode),entries)
            altered=bytearray(packed)
            altered[-1]^=1
            with self.assertRaises(ValueError):
                decode(bytes(altered),mode)

    def test_trailing_and_out_of_range_ids(self):
        entries=[{'sha':'0'*64,'size':1,'frames':[{'sha':'1'*64,'len':1}]}]
        packed=pack_binary(entries,True)
        with self.assertRaises(ValueError):
            unpack_binary(packed+b'x',True)
        with self.assertRaises(ValueError):
            unpack_binary(packed[:-1],True)

    def test_actual_versions_all_24_layouts(self):
        docs=prior().load_source()
        self.assertEqual(len(docs),12)
        result=measure(docs,queries_per_version=3)
        self.assertEqual(len(result['results']),4)
        self.assertTrue(all(len(methods)==6 for methods in result['results'].values()))
        for mode in result['results']:
            self.assertLess(result['results'][mode]['json-zlib']['serialized_manifest_bytes'],
                            result['results'][mode]['json']['serialized_manifest_bytes'])

if __name__=='__main__':
    unittest.main()
