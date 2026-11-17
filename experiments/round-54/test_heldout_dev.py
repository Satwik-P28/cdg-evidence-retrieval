import unittest
from copy import deepcopy
from heldout_dev import (aggregate,graph_rank,locked_sample,question_gate,
                         support_reference_issue,integrity_audit,
                         select,SAMPLE_SALT,FROZEN_K,URL,SHA256)


def row(tag,title='Founder',typ='bridge'):
    return {
        '_id':tag,
        'question':'Which film did Founder direct?',
        'context':[
            ['Founder',['Founder directed Film B in 1990.']],
            ['Film B',['Film B was released in 1992.']],
            ['Film A',['Different film was released.']],
            ['Film C',['Unrelated film.']],
            ['Film D',['Another unrelated film.']],
        ],
        'supporting_facts':[['Founder',0],['Film B',0]],
        'type':typ,'answer':'Film B',
    }


class HeldoutTests(unittest.TestCase):
    def test_source_is_revision_and_sha_pinned(self):
        self.assertIn('7e54db4656209750ff487f6fdf8e39a66dba136b',URL)
        self.assertEqual(len(SHA256),64)

    def test_locked_sampling_order_independent(self):
        rows=[row('id-'+str(i)) for i in range(10)]
        first=[r['_id'] for r in locked_sample(rows,5)]
        second=[r['_id'] for r in locked_sample(list(reversed(rows)),5)]
        self.assertEqual(first,second)
        self.assertEqual(len(first),5)
        self.assertTrue(SAMPLE_SALT)
        with self.assertRaises(ValueError):
            locked_sample(rows+rows[:1],5)

    def test_graph_and_original_bridge_same(self):
        example=row('a')
        self.assertEqual(graph_rank(example),select(example,'bridge'))
        example['context'][0][1][0]='Film-C and Film B are referenced.'
        self.assertEqual(graph_rank(example),select(example,'bridge'))

    def test_question_text_gate_never_reads_gold_type(self):
        base=row('a')
        a=select(base,'text_gate')
        copy=deepcopy(base)
        copy['type']='comparison'
        copy['supporting_facts']=[['Film C',0]]
        copy['answer']='Fake'
        self.assertEqual(a,select(copy,'text_gate'))
        self.assertTrue(question_gate('Are X and Y both films?'))
        self.assertFalse(question_gate('Which film did Founder direct?'))

    def test_aggregation_complete_docs_and_pair(self):
        examples=[row('a'),row('b',typ='comparison')]
        outcome=aggregate(examples)
        self.assertEqual(outcome['n'],2)
        self.assertEqual(set(outcome['methods']),
                         {'bm25','bridge','mmr','title_graph','text_gate'})
        for policy in outcome['methods']:
            for k in map(str,FROZEN_K):
                self.assertEqual(outcome['methods'][policy][k]['n'],2)
                self.assertGreaterEqual(outcome['methods'][policy][k]['complete_docs'],0)
        for k,counts in outcome['paired_bm25_bridge'].items():
            self.assertEqual(sum(counts.values()),2)

    def test_annotation_faults_not_silently_filtered(self):
        bad=row('bad')
        bad['supporting_facts']=[['Absent source',0]]
        out=aggregate([row('valid'),bad])
        self.assertEqual(out['n'],2)
        self.assertEqual(out['unscorable_support_count'],1)
        self.assertEqual(support_reference_issue(bad),'missing_document')
        for method in out['methods']:
            self.assertLessEqual(out['methods'][method]['5']['complete_docs'],1)
        bad2=row('bad2')
        bad2['supporting_facts']=[['Founder',900]]
        self.assertEqual(support_reference_issue(bad2),'missing_sentence')
        self.assertEqual(integrity_audit([row('ok'),bad,bad2])['counts'],
                         {'valid':1,'missing_document':1,'missing_sentence':1})

    def test_report_has_no_answers_or_gold_ids_in_query_output(self):
        result=aggregate([row('x')])
        self.assertNotIn('per_question',result)
        self.assertNotIn('answer',result)
        self.assertEqual(len(result['sample_id_sha256']),64)


if __name__=='__main__':
    unittest.main()
