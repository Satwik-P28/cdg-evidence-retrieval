import tempfile,unittest
from relatedness_gate import (THRESHOLDS,windows,online_relatedness,
                              evaluate,load,R46,R47,R58)


class GateTests(unittest.TestCase):
    def test_byte_shingles_ignore_labels_and_detect_edits(self):
        common=(b'document history and common text'*60)
        different=(b'quantum field unrelated bytes 123'*55)
        documents=[('history',common),('independent',common[:-20]+b'modification'),
                   ('history',different),('independent',different)]
        scores=online_relatedness(documents)
        self.assertEqual(scores[0],0)
        self.assertGreater(scores[1],.5)
        self.assertLess(scores[2],.20)
        self.assertGreater(scores[3],.8)
        # Labels must not be passed to the gate.
        relabeled=[('independent' if group=='history' else 'history',blob)
                   for group,blob in documents]
        self.assertEqual(scores,online_relatedness(relabeled))

    def test_frozen_thresholds(self):
        self.assertEqual(THRESHOLDS,(.20,.50,.80))
        self.assertGreater(len(windows(b'raw input'*100)),1)
        self.assertEqual(len(windows(b'one')),1)
        self.assertEqual(windows(b'one'),windows(b'one'))

    def test_gating_backwards_compatible_with_original_online(self):
        r58=load('cdg58_unittest63',R58)
        r46=load('cdg46_unittest63',R46)
        r47=load('cdg47_unittest63',R47)
        docs=[('history',b'abc'*1200),('history',b'abc'*1000+b'xyz'*200),
              ('independent',b'unrelated file'),
              ('independent',b'totally different file')]
        control=r58.MixedStore(docs,'online_read_weighted',r46.frame,r47)
        allow=r58.MixedStore(docs,'online_read_weighted',r46.frame,r47,
                             gear_allowed=[True]*len(docs))
        never=r58.MixedStore(docs,'online_read_weighted',r46.frame,r47,
                             gear_allowed=[False]*len(docs))
        whole=r58.MixedStore(docs,'all_whole',r46.frame,r47)
        self.assertEqual(control.archive_bytes(),allow.archive_bytes())
        self.assertEqual(control.methods,allow.methods)
        self.assertEqual(never.archive_bytes(),whole.archive_bytes())
        self.assertTrue(all(x=='whole' for x in never.methods))
        for i,(_,blob) in enumerate(docs):
            self.assertEqual(never.read(i,0,len(blob))[0],blob)
        with self.assertRaises(ValueError):
            r58.MixedStore(docs,'online_read_weighted',r46.frame,r47,
                           gear_allowed=[True])

    def test_gating_matrix_with_fixture(self):
        histories={
            'ruff':[{'data':b'ruff updated doc\n'*100+b'version x'},
                    {'data':b'ruff updated doc\n'*100+b'version y'}],
            'transformers':[{'data':b'long transformer README\n'*100+b'v1'},
                            {'data':b'long transformer README\n'*100+b'v2'}],
            'flask':[{'data':b'flask manual\n'*100+b'v1'},
                     {'data':b'flask manual\n'*100+b'v2'}]}
        independent=[('independent',f'fresh source {i}'.encode()) for i in range(512)]
        import relatedness_gate as m
        old=m.IND_COUNTS
        m.IND_COUNTS=(128,)
        try:
            result=evaluate(histories,independent)
        finally:
            m.IND_COUNTS=old
        self.assertEqual(result['total_scenarios'],3*1*len(THRESHOLDS))
        for row in result['scenarios']:
            self.assertLessEqual(row['history_gear_selected'],row['history_eligible'])
            self.assertEqual(row['independent_gear_selected'],0)

if __name__=='__main__':unittest.main()
