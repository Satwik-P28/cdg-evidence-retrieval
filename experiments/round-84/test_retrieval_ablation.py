import io,json,tarfile,unittest
from retrieval_ablation import (
    annotated_claims,query_tokens,compute_metrics,choose_on_train,
    bootstrap_delta,fts_rank_all,train_claims_from_verified_archive,
    variant_name,VARIANTS
)


class BM25AblationContracts(unittest.TestCase):
    def test_gold_source_only_label_selection(self):
        cases=[
          {'id':1,'claim':'A','evidence':{'5':[{'label':'SUPPORT','sentences':[0]}]}},
          {'id':2,'claim':'B','evidence':{}},
          {'id':3,'claim':'C','evidence':{'9':[{'label':'CONTRADICT','sentences':[1]}]}},
        ]
        selected=annotated_claims(cases,{'5','11'})
        self.assertEqual(len(selected),1)
        self.assertEqual(selected[0]['gold'],{'5'})
        self.assertEqual(compute_metrics(selected,{'1':['99','5']})['recall_at_1'],0)
        self.assertEqual(compute_metrics(selected,{'1':['99','5']})['recall_at_3'],1)

    def test_term_budget_and_or_escaping(self):
        x='A doctor writes about T-cell T-cell effects in PCR and qPCR tests.'
        short=query_tokens(x,3)
        full=query_tokens(x,28)
        self.assertLessEqual(len(short),3)
        self.assertGreaterEqual(len(full),len(short))
        self.assertEqual(len(set(full)),len(full))
        self.assertEqual(len(VARIANTS),8)
        self.assertEqual(variant_name(5.0,28),'fts_title5_terms28')
        with self.assertRaises(ValueError):
            variant_name(7.0,28)

    def test_all_variants_same_corpus_and_index(self):
        corpus=[
            {'doc_id':100,'title':'Neonatal plasma','abstract':['Blood plasma and cell markers.']},
            {'doc_id':200,'title':'Antibiotic resistance','abstract':['Bacteria resist therapy.']},
            {'doc_id':300,'title':'Control condition','abstract':['Unrelated molecules.']},
        ]
        queries=[{'id':5,'claim':'Neonatal plasma blood study'}]
        result,cost=fts_rank_all(corpus,queries,10)
        self.assertEqual(len(result),8)
        self.assertTrue(all('5' in v for v in result.values()))
        self.assertTrue(all(r['5'][0]=='100' for r in result.values()))
        self.assertGreater(cost['index_bytes'],0)

    def test_train_only_choice_ignores_dev(self):
        a='fts_title1_terms12'
        b='fts_title5_terms28'
        train=[{'id':str(i),'gold':{str(i)}} for i in range(10)]
        ranks={
            a:{r['id']:[r['id']] for r in train},
            b:{r['id']:['x',r['id']] for r in train},
        }
        metrics={
            a:{'train':compute_metrics(train,ranks[a]),'dev':{'recall_at_5':0.,'recall_at_1':0.}},
            b:{'train':compute_metrics(train,ranks[b]),'dev':{'recall_at_5':1.,'recall_at_1':1.}},
        }
        self.assertEqual(choose_on_train(train,ranks,metrics),a)
        metrics[a]['dev']={'recall_at_5':1.0,'recall_at_1':1.0}
        self.assertEqual(choose_on_train(train,ranks,metrics),a)

    def test_bootstrap_direction_and_train_tar_schema(self):
        rows=[{'id':str(i),'gold':{str(i)}} for i in range(30)]
        original={r['id']:['other'] for r in rows}
        improved={r['id']:[r['id']] for r in rows}
        out=bootstrap_delta(rows,original,improved,k=1,reps=100)
        self.assertEqual(out['delta_recall_b_minus_a'],1.)
        self.assertEqual(out['paired_n'],30)
        buff=io.BytesIO()
        payload=(json.dumps({'id':1,'claim':'X','evidence':{}})+'\n').encode()
        with tarfile.open(fileobj=buff,mode='w:gz') as tf:
            meta=tarfile.TarInfo('data/claims_train.jsonl')
            meta.size=len(payload)
            tf.addfile(meta,io.BytesIO(payload))
        data,meta=train_claims_from_verified_archive(buff.getvalue())
        self.assertEqual(data[0]['id'],1)
        self.assertEqual(meta['original_train_rows'],1)


if __name__=='__main__':
    unittest.main()
