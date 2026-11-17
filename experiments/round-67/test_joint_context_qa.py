import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from joint_context_qa import (
    budget_prefix,join_materials,prepare_tasks,make_oracle_task,locate_source_answer,
    experiment,aggregate,K_VALUES,MODES,POLICIES,
)
import extractive_qa as r66


def row(id='q',answer='Film B'):
    return {
        '_id':id,'question':'What film did Founder direct?',
        'context':[
            ['Founder',['Founder lived in London.','Founder directed Film B.']],
            ['Film B',['Film B is a drama.','Film B was released.']],
            ['Film C',['This is not the film.']],
            ['Film D',['A different movie unrelated.']],
            ['Film E',['One more title in a candidate pool.']],
        ],
        'supporting_facts':[['Founder',1],['Film B',0]],
        'answer':answer,'type':'bridge',
    }


class TinyTokenizer:
    def __call__(self,question,context,**kwargs):
        return {'input_ids':list(range(4+len(context.split())))}


class CountCharTokenizer:
    def __call__(self,question,context,**kwargs):
        return {'input_ids':list(range(4+len(context)))}


class FakeReader:
    def __init__(self):
        self.last_inputs=[]
    def __call__(self,inputs,**kwargs):
        self.last_inputs=inputs
        return [{'answer':'Film B' if 'Film B' in task['context'] else '',
                 'score':.9 if 'Film B' in task['context'] else 0.0}
                for task in inputs]


class JointTests(unittest.TestCase):
    def test_strict_char_preserving_prefix(self):
        question='Where?'
        text='😊 ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        got,count,cut=budget_prefix(question,text,CountCharTokenizer(),12)
        self.assertTrue(cut)
        self.assertEqual(count,12)
        self.assertEqual(got,text[:8])
        uncut,n,b=budget_prefix(question,'hello',CountCharTokenizer(),12)
        self.assertEqual(uncut,'hello')
        self.assertFalse(b)

    def test_concat_and_evidence_position_map(self):
        first={'context':'alpha beta','title':'A',
               'snippets':[{'text':'alpha','lo':0,'hi':5},
                           {'text':'beta','lo':5,'hi':9}]}
        second={'context':'gamma','title':'B',
                'snippets':[{'text':'gamma','lo':0,'hi':5}]}
        result,spans=join_materials([
            (0,first,[0,1]),(1,second,[0])])
        self.assertEqual(result,'alpha beta\n\ngamma')
        self.assertEqual(spans,[('A',0,0,5),('A',1,6,10),('B',0,12,17)])
        with self.assertRaises(AssertionError):
            join_materials([(0,first,[0])])

    def test_source_and_gold_diagnostic_separation(self):
        rows=[row()]
        r55=r66.load('cdg55_test67',r66.R55)
        r48=r66.load('cdg48_test67',r66.R48)
        with TemporaryDirectory() as tmp:
            index=r55.SentenceIndex(Path(tmp)/'s.sqlite',rows)
            readers={
                'whole':r48.VersionedReader(index.original_blobs,'whole','json-zlib'),
                'gear512':r48.VersionedReader(index.original_blobs,'gear512','binary-zlib')}
            try:
                tasks=prepare_tasks(rows,index,readers,TinyTokenizer())
                self.assertEqual(len(tasks),3*2*len(MODES)*1+1)
                oracle=[t for t in tasks if t['oracle']][0]
                self.assertIn('Founder directed Film B.',oracle['context'])
                normal=[t for t in tasks if not t['oracle']]
                self.assertTrue(any(t['policy']=='bm25' for t in normal))
                self.assertTrue(all(t['tokens']<=384 for t in tasks))
                self.assertTrue(locate_source_answer('Film B',oracle,readers))
                self.assertFalse(locate_source_answer('fabrication',oracle,readers))
            finally:index.close()

    def test_fake_full_reader_pipeline(self):
        reader=FakeReader()
        cases=[row('a'),row('b')]
        outcome=experiment(cases,TinyTokenizer(),reader,
                           {'id':'fixture','revision':'0'*40})
        self.assertEqual(outcome['questions'],2)
        self.assertEqual(outcome['actual_model_calls'],26)
        self.assertEqual(len(reader.last_inputs),26)
        self.assertEqual(len(outcome['conditions']),
                         len(POLICIES)*len(K_VALUES)*len(MODES)*2+2)
        for item in outcome['conditions']:
            self.assertLessEqual(item['answer_em_count'],item['n'])
            self.assertLessEqual(item['correct_answer_and_complete_gold_evidence'],
                                 item['answer_em_count'])
            self.assertGreaterEqual(item['mean_tokenizer_input_tokens'],0)
        self.assertGreater(outcome['source_index_bytes'],0)

    def test_gold_change_affects_only_oracle_and_scoring(self):
        first=row('x')
        altered=row('x',answer='Completely Different')
        altered['supporting_facts']=[['Film D',0]]
        r55=r66.load('cdg55_gold67',r66.R55)
        r48=r66.load('cdg48_gold67',r66.R48)
        with TemporaryDirectory() as home:
            a=r55.SentenceIndex(Path(home)/'first.sqlite',[first])
            b=r55.SentenceIndex(Path(home)/'second.sqlite',[altered])
            try:
                make=lambda idx:{
                    'whole':r48.VersionedReader(idx.original_blobs,'whole','json-zlib'),
                    'gear512':r48.VersionedReader(idx.original_blobs,'gear512','binary-zlib')}
                contexts_a=prepare_tasks([first],a,make(a),TinyTokenizer())
                contexts_b=prepare_tasks([altered],b,make(b),TinyTokenizer())
                normal_a=[(t['policy'],t['mode'],t['documents'],t['context'])
                          for t in contexts_a if not t['oracle']]
                normal_b=[(t['policy'],t['mode'],t['documents'],t['context'])
                          for t in contexts_b if not t['oracle']]
                self.assertEqual(normal_a,normal_b)
                self.assertNotEqual(contexts_a[-1]['context'],contexts_b[-1]['context'])
            finally:a.close();b.close()

if __name__=='__main__':
    unittest.main()
