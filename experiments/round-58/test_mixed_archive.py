import unittest
from mixed_archive import (MixedStore,ordered_sources,exercise,load,
                           R46,R47,METHODS,POLICIES,ORDERS)


class MixedTests(unittest.TestCase):
    def setUp(self):
        self.old=load('cdg_r46_test58',R46)
        self.packer=load('cdg_r47_test58',R47)
        self.h=[('history',b'café 😊 '+b'a'*1300),
                ('history',b'café 😊 '+b'a'*1000+b'b'*300)]
        self.u=[('independent',b'new source one'),
                ('independent',b'another independent source'),
                ('independent',b'third topic evidence'),
                ('independent',b'the last unique document')]

    def test_policy_exact_reconstruction_and_digest(self):
        docs=self.h+self.u
        for method in POLICIES:
            store=MixedStore(docs,method,self.old.frame,self.packer)
            for i,(_,blob) in enumerate(docs):
                self.assertEqual(store.read(i,0,len(blob))[0],blob)
                self.assertEqual(store.read(i,1,min(32,len(blob)))[0],
                                 blob[1:min(32,len(blob))])
            self.assertGreater(store.archive_bytes(),0)
            self.assertEqual(sum(store.methods.count(m) for m in METHODS),len(docs))
            with self.assertRaises(ValueError):
                store.read(0,-1,5)

    def test_corrupt_archive_content_is_rejected(self):
        store=MixedStore(self.h,'all_gear512',self.old.frame,self.packer)
        item=store.manifests[0]['frames'][0]['sha']
        store.payloads[item]=b'garbled compressed bytes'
        with self.assertRaises(Exception):
            store.read(0,0,len(self.h[0][1]))
        store=MixedStore(self.h,'all_whole',self.old.frame,self.packer)
        store.serialized+=b'corrupt'
        with self.assertRaises(ValueError):
            store.read(0,0,5)

    def test_input_order_ablation_and_negative_control(self):
        result=exercise(self.h,self.u)
        self.assertEqual(len(result['strategies']),len(ORDERS)*len(POLICIES))
        self.assertEqual(result['total_sources'],6)
        for row in result['strategies']:
            self.assertEqual(row['sources'],6)
            self.assertEqual(row['queries'],12)
            self.assertGreaterEqual(row['mean_compressed_frame_bytes'],0)
        # Fixed modes consume the same raw multiset independent of source order;
        # the exact compression of manifests can still vary due to row ordering.
        for mode in ('all_whole','all_gear512'):
            totals=[x['mean_compressed_frame_bytes'] for x in result['strategies']
                    if x['policy']==mode]
            self.assertEqual(len(totals),3)
            self.assertTrue(max(totals)-min(totals)<1e-6,totals)

if __name__=='__main__':
    unittest.main()
