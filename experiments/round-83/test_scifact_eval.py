import unittest
from scifact_eval import (
    doc_text,source_claim_labels,select_gold,tfidf_ranks,fts5_ranks,
    retrieval_metrics,verify_archived_evidence,classify_predictions
)


def paper(i):
    return {'doc_id':i,'title':f'Paper {i} influenza therapy trials',
            'abstract':[f'Therapy {i} has a measured laboratory outcome.'],
            'structured':False}


def claim(i,label):
    return {'id':i,'claim':f'Therapy {i} has a measured laboratory outcome.',
            'evidence':{str(i):[{'label':label,'sentences':[0]}]},
            'cited_doc_ids':[i]}


class SciFactRetrievalTests(unittest.TestCase):
    def test_doc_text_and_original_label_contract(self):
        c=paper(2)
        self.assertIn(c['title'],doc_text(c))
        self.assertIn(c['abstract'][0],doc_text(c))
        lab=source_claim_labels(claim(2,'CONTRADICT'))
        self.assertEqual(lab,{'2':'CONTRADICT'})

    def test_gold_sampling_disjoint_source_and_claim_groups(self):
        claims=[claim(i,'SUPPORT' if i%2 else 'CONTRADICT') for i in range(80)]
        chosen,digest=select_gold(claims,{str(i) for i in range(80)})
        self.assertEqual(len(chosen),60)
        self.assertEqual(len({x['gold_doc_id'] for x in chosen}),60)
        self.assertEqual(len({x['claim_id'] for x in chosen}),60)
        self.assertEqual(sum(x['supported'] for x in chosen),30)
        self.assertEqual(len(digest),64)

    def test_tfidf_and_bm25_are_label_blind_retrievers(self):
        corpus=[
            {'doc_id':1,'title':'Cancer tumors and response',
             'abstract':['Tumor therapy reduces cancer.']},
            {'doc_id':2,'title':'Mammal migration nesting',
             'abstract':['Bird migration and habitat.']},
            {'doc_id':3,'title':'Cardiac heart function',
             'abstract':['Heart valves and heart rhythm.']},
        ]
        rows=[{'id':10,'claim':'cardiac heart rhythm effect',
               'evidence':{'3':[{'label':'SUPPORT','sentences':[0]}]}}]
        tf,tf_stats=tfidf_ranks(corpus,rows,3)
        fts,fts_stats=fts5_ranks(corpus,rows,3)
        self.assertEqual(tf['10'][0],'3')
        self.assertEqual(fts['10'][0],'3')
        self.assertEqual(retrieval_metrics(rows,{'1','2','3'},tf)
                         ['all']['recall']['recall_at_1']['hits'],1)
        self.assertGreater(fts_stats['persistent_index_bytes'],0)
        self.assertGreater(tf_stats['vocabulary_terms'],0)

    def test_archive_and_no_wrong_source_label_leakage(self):
        corpus=[paper(1),paper(2)]
        row={'claim_id':'20','gold_doc_id':'1',
             'claim':'Therapy 1 has outcome.','supported':1,'label':'SUPPORT',
             'gold_doc_labels':{'1':'SUPPORT'}}
        tf={'20':['2']};fts={'20':['1']}
        routes,cost=verify_archived_evidence(corpus,[row],tf,fts)
        self.assertEqual(cost['archives']['whole']['route_source_readbacks'],3)
        self.assertEqual(cost['archives']['gear512']['route_source_readbacks'],3)
        self.assertTrue(routes['gold_oracle'][0]['selected_doc_has_annotation'])
        self.assertFalse(routes['tfidf_top1'][0]['selected_doc_has_annotation'])
        flat=[{**r,'route':policy}
              for policy,rows in routes.items() for r in rows]
        scores=classify_predictions(flat,[.9,.9,.9],'synthetic')
        self.assertEqual(scores['tfidf_top1']['human_annotated_doc_pairs'],0)
        self.assertEqual(scores['tfidf_top1']['no_human_label_for_selected_doc_pairs'],1)
        self.assertEqual(scores['tfidf_top1']['only_annotated_pairs_confusion']['tp'],0)
        self.assertEqual(scores['gold_oracle']['only_annotated_pairs_confusion']['tp'],1)

if __name__=='__main__':
    unittest.main()
