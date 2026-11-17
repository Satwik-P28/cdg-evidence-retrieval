import tempfile
import unittest
from pathlib import Path
from heldout_frames import SentenceIndex,experiment,selected_query_trace,CONFIGS


def row(tag,question='Which film did Founder direct?'):
    return {'_id':tag,'question':question,
            'context':[
                ['Founder',['Café 😊 Founder directed Film B.','The inventor lived abroad.']],
                ['Film B',['Film B was directed by Founder.','The movie was released.']],
                ['Film C',['Film C has a different director.']],
                ['Film D',['This movie has no known connection.']],
                ['Film E',['Another random movie.']]],
            'supporting_facts':[['Founder',0],['Film B',0]],
            'answer':'Film B','type':'bridge'}


class IntegrationTests(unittest.TestCase):
    def test_index_uses_exact_utf8_offsets(self):
        data=[row('A')]
        with tempfile.TemporaryDirectory() as tmp:
            idx=SentenceIndex(Path(tmp)/'idx.sqlite',data)
            try:
                self.assertEqual(len(idx.original_blobs),5)
                key=idx.records[(0,0)]
                self.assertIn('😊'.encode(),idx.original_blobs[key])
                hits=idx.choose(0,0,'Founder directed')
                for sid,lo,hi in hits:
                    self.assertEqual(idx.original_blobs[key][lo:hi],
                                     data[0]['context'][0][1][sid].encode())
                self.assertGreater(idx.db_bytes,0)
            finally:
                idx.close()

    def test_policy_source_selection_does_not_require_gold(self):
        a=row('A')
        b=row('B')
        b['supporting_facts']=[['Film D',0]]
        with tempfile.TemporaryDirectory() as tmp:
            idx=SentenceIndex(Path(tmp)/'idx.sqlite',[a,b])
            try:
                selections,_=selected_query_trace([a,b],idx)
                self.assertEqual(selections[(0,'bm25')]['ranked_docs'],
                                 selections[(1,'bm25')]['ranked_docs'])
                self.assertEqual(selections[(0,'bridge')]['ranked_docs'],
                                 selections[(1,'bridge')]['ranked_docs'])
            finally:
                idx.close()

    def test_complete_small_integrated_run(self):
        rows=[row('x'),row('y','What film did Founder make?')]
        result=experiment(rows)
        self.assertEqual(result['sample_size'],2)
        self.assertEqual(result['documents_archived'],10)
        self.assertEqual(set(result['frame_methods']),set(CONFIGS))
        for method,stats in result['frame_methods'].items():
            self.assertGreater(stats['archive_bytes'],0)
            self.assertGreater(stats['sentence_index_bytes'],0)
            for policy in ('bridge','bm25'):
                self.assertEqual(stats['policies'][policy]['2']['questions'],2)
                self.assertGreaterEqual(stats['policies'][policy]['5']['mean_compressed_bytes_full_documents'],0)
                self.assertGreaterEqual(stats['policies'][policy]['5']['mean_compressed_bytes_selected_sentences_gross'],0)

if __name__=='__main__':
    unittest.main()
