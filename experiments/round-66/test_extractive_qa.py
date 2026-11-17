import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from extractive_qa import (
    exact_match,token_f1,normalize_answer,random_docs,validate_model_lock,
    make_context,citation_for_answer,experiment,compressed_keys,load,
    R48,R55,MODES,DOCUMENT_LIMITS,POLICIES,THRESHOLDS,
)


def fixture_row(identifier='a',reference='Film B'):
    return {
        '_id':identifier,
        'question':'Which film did Founder direct?',
        'context':[
            ['Founder',['Founder lived in Paris.','Founder directed Film B.']],
            ['Film B',['Film B was directed by Founder.','Film B is also a drama.']],
            ['Film C',['Film C was a comedy.']],
            ['Film D',['An unrelated sentence appears here.']],
            ['Film E',['This is another independent source.']],
        ],
        'answer':reference,
        'type':'bridge',
        'supporting_facts':[['Founder',1],['Film B',0]],
    }


class FakeTokenizer:
    def __call__(self,question,context,**options):
        return {'input_ids':list(range(10+len(context.split())))}


class FakeReader:
    def __init__(self):
        self.calls=[]
    def __call__(self,inputs,**kwargs):
        self.calls.append(len(inputs))
        values=[]
        for inp in inputs:
            text=inp['context']
            answer='Film B' if 'Film B' in text else ''
            values.append({'answer':answer,'score':.83 if answer else .0})
        return values


class Round66Tests(unittest.TestCase):
    def test_official_style_answer_metrics(self):
        self.assertEqual(normalize_answer('The, Film!'),'film')
        self.assertEqual(exact_match('the film!','Film'),1)
        self.assertEqual(exact_match('yes','no'),0)
        self.assertEqual(token_f1('yes','no'),0)
        self.assertEqual(token_f1('',''),1)
        self.assertAlmostEqual(token_f1('New York City','York City'),.8)
        self.assertEqual(token_f1('The Answer','unrelated'),0)

    def test_immutable_model_lock_enforced(self):
        self.assertEqual(validate_model_lock({
            'name':'deepset/tinyroberta-squad2','revision':'a'*40}),'a'*40)
        for lock in (
            {'name':'deepset/tinyroberta-squad2','revision':'main'},
            {'name':'wrong/model','revision':'a'*40},
            {'name':'deepset/tinyroberta-squad2','revision':'0'*39},
        ):
            with self.assertRaises(ValueError):validate_model_lock(lock)

    def test_negative_controls_cannot_see_gold(self):
        row=fixture_row()
        altered=fixture_row(reference='Completely Different')
        altered['supporting_facts']=[['Film D',0]]
        self.assertEqual(random_docs(row,2),random_docs(altered,2))
        self.assertEqual(len(random_docs(row,5)),5)

    def test_exact_source_receipts_are_not_only_string_matches(self):
        r55=load('cdg55_test66',R55)
        r48=load('cdg48_test66',R48)
        row=fixture_row()
        with TemporaryDirectory() as tmp:
            index=r55.SentenceIndex(Path(tmp)/'fts.sqlite',[row])
            try:
                readers={
                    'whole':r48.VersionedReader(index.original_blobs,'whole','json-zlib'),
                    'gear512':r48.VersionedReader(index.original_blobs,'gear512','binary-zlib')}
                for mode in MODES:
                    material=make_context(index,readers,row,0,0,mode)
                    self.assertGreater(material['source'], -1)
                    self.assertGreaterEqual(material['context_utf8_bytes'],0)
                    self.assertEqual(set(material['unique_frame_ids']),set(readers))
                    if 'Film B' in material['context']:
                        citation=citation_for_answer('Film B',material,readers['whole'])
                        self.assertIsNotNone(citation)
                        self.assertEqual(citation['byte_end']-citation['byte_start'],
                                         len('Film B'.encode()))
                    self.assertIsNone(citation_for_answer(
                        'fabricated answer',material,readers['whole']))
                m=readers['whole'].manifests[0]
                self.assertEqual(compressed_keys(m,0,m['size']),
                                 {f['sha'] for f in m['frames']})
            finally:
                index.close()

    def test_full_pipeline_without_model_download(self):
        tokenizer=FakeTokenizer();reader=FakeReader()
        result=experiment(
            [fixture_row('a'),fixture_row('b')],
            tokenizer,reader,{
                'id':'fixture','revision':'f'*40,
                'device':'fake','max_seq_length':384})
        self.assertEqual(result['count'],2)
        self.assertEqual(result['actual_reader_inference_calls'],20)
        self.assertEqual(len(result['observations']),
                         len(POLICIES)*len(DOCUMENT_LIMITS)*len(MODES)*len(THRESHOLDS))
        self.assertEqual(result['uncitable_model_candidates_rejected'],0)
        self.assertEqual(len(reader.calls),1)
        for row in result['observations']:
            self.assertEqual(row['n'],2)
            self.assertLessEqual(row['complete_gold_evidence'],row['complete_gold_docs'])
            self.assertGreaterEqual(row['mean_model_input_tokens_if_uncached'],0)
            self.assertGreaterEqual(row['mean_unique_compressed_bytes_whole'],0)
        self.assertGreater(result['source_index_bytes'],0)
        self.assertGreater(result['source_archive_bytes']['whole'],0)

    def test_gold_label_swap_does_not_change_reader_inputs(self):
        tokenizer=FakeTokenizer()
        a=fixture_row()
        b=fixture_row(reference='Unrelated Answer')
        b['supporting_facts']=[['Film D',0]]
        first=FakeReader();second=FakeReader()
        out1=experiment([a],tokenizer,first,{'id':'fixture'})
        out2=experiment([b],tokenizer,second,{'id':'fixture'})
        self.assertEqual(first.calls,second.calls)
        for x,y in zip(out1['observations'],out2['observations']):
            self.assertEqual(x['mean_model_input_tokens_if_uncached'],
                             y['mean_model_input_tokens_if_uncached'])
            self.assertEqual(x['mean_unique_compressed_bytes_whole'],
                             y['mean_unique_compressed_bytes_whole'])

if __name__=='__main__':
    unittest.main()
