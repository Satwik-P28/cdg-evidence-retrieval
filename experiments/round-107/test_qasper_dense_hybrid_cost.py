"""R107 frozen dense evidence source scopes and label-free fusion tests."""
import unittest

from qasper_dense_hybrid_cost import (
    MODEL_SPECS,RRF_K,ensure_original_source_docs,
    dense_rank,rrf_rank,fuse_cases,evidence_metrics,paper_cluster_bootstrap
)


DOCS=[
    {"doc_id":str(i),"title":"Results "+str(i),
     "abstract":["The original scientific source stated paragraph "+str(i)]}
    for i in range(1,6)
]
CASES=[
    {"id":"c1","paper":"paperA","claim":"a source question",
     "row_start":1,"row_end":3,"gold_rowids":{2}},
    {"id":"c2","paper":"paperB","claim":"a second source question",
     "row_start":4,"row_end":5,"gold_rowids":{5}},
    {"id":"c3","paper":"paperA","claim":"no exact original evidence",
     "row_start":1,"row_end":3,"gold_rowids":set()},
]


class DenseGoldContractTests(unittest.TestCase):
    def test_two_pretrained_checkpoints_revision_sha_pinned(self):
        self.assertEqual(set(MODEL_SPECS),{
            "MiniLM-L6","BGE-small-v1.5"})
        for spec in MODEL_SPECS.values():
            self.assertEqual(len(spec["revision"]),40)
            self.assertIn(spec["pool"],{"mean","cls"})
        self.assertNotEqual(
            MODEL_SPECS["MiniLM-L6"]["pool"],
            MODEL_SPECS["BGE-small-v1.5"]["pool"])

    def test_original_source_bytes_sha_contract(self):
        metadata=ensure_original_source_docs(DOCS)
        self.assertEqual(metadata["source_documents_exact"],5)
        self.assertEqual(metadata["source_sha256_receipts"],5)
        self.assertGreater(metadata["original_raw_bytes"],0)

    def test_original_source_ids_must_be_unique(self):
        with self.assertRaises(AssertionError):
            ensure_original_source_docs(DOCS+[DOCS[0]])

    def test_dense_rank_paper_restriction(self):
        import numpy as np
        # Scores are chosen to force 2 > 1 > 3, and 5 > 4,
        # with a globally largest value in a different paper.
        sources=np.array([
            [1,0],[0,1],[-1,0],[1,0],[0,1]],dtype="float32")
        queries=np.array([[0,1],[0,1],[1,0]],dtype="float32")
        actual,_=dense_rank(CASES,sources,queries)
        self.assertEqual(actual["c1"],[2,1,3])
        self.assertEqual(actual["c2"],[5,4])
        self.assertEqual(set(actual["c3"]),{1,2,3})

    def test_dense_rank_zero_document_range_gives_empty_not_other_paper(self):
        import numpy as np
        x=[{"id":"empty","paper":"p","row_start":5,"row_end":4}]
        source=np.array([[1,0]],dtype="float32")
        queries=np.array([[1,0]],dtype="float32")
        actual,_=dense_rank(x,source,queries)
        self.assertEqual(actual["empty"],[])

    def test_dense_nonfinite_scores_rejected(self):
        import numpy as np
        sources=np.ones((5,2),dtype="float32")
        sources[1,0]=np.nan
        queries=np.ones((3,2),dtype="float32")
        with self.assertRaises(AssertionError):
            dense_rank(CASES,sources,queries)

    def test_rrf_order_deterministic_and_label_free(self):
        a=rrf_rank([[2,1,3],[1,2,3]],RRF_K)
        b=rrf_rank([[2,1,3],[1,2,3]],RRF_K)
        self.assertEqual(a,b)
        self.assertEqual(set(a),{1,2,3})
        # Equal scores tie by original source rowid.
        self.assertEqual(a[0],1)

    def test_rrf_reject_duplicate_source_in_rank_list(self):
        with self.assertRaises(AssertionError):
            rrf_rank([[1,1,2],[2,3,1]],RRF_K)

    def test_rrf_reject_no_sources_or_negative_rank_constant(self):
        with self.assertRaises(ValueError):
            rrf_rank([])
        with self.assertRaises(ValueError):
            rrf_rank([[1,2]],0)

    def test_fusion_scoped_to_original_cases(self):
        rankings={
            "bm25":{"c1":[3,2,1],"c2":[4,5],"c3":[1,2,3]},
            "dense":{"c1":[2,1,3],"c2":[5,4],"c3":[2,1,3]},
        }
        result=fuse_cases(rankings,CASES)
        self.assertEqual(len(result),3)
        self.assertEqual(set(result["c1"]),{1,2,3})
        self.assertEqual(set(result["c2"]),{4,5})

    def test_human_evidence_only_eligible_denominator(self):
        ranks={"c1":[2,1,3],"c2":[5,4],"c3":[1,2,3]}
        x=evidence_metrics(CASES,ranks)
        rate=x["any_one_gold_paragraph_recall"]["recall"]["r1"]
        self.assertEqual(rate["hits"],2)
        self.assertEqual(rate["denominator"],2)
        self.assertEqual(x["gold_annotator_union_paragraph_coverage"][
            "1"]["gold_paragraph_union_denominator"],2)

    def test_paper_cluster_bootstrap_reports_negative_delta(self):
        incumbent={"c1":[2,1,3],"c2":[5,4],"c3":[1,2,3]}
        candidate={"c1":[1,3,2],"c2":[4,5],"c3":[2,1,3]}
        x=paper_cluster_bootstrap(
            CASES,candidate,incumbent,k=1,reps=50)
        self.assertEqual(x["eligible_questions"],2)
        self.assertEqual(x["clusters"],2)
        self.assertEqual(x["delta_fraction"],-1.0)

    def test_rrf_fusion_not_automatically_assumed_superior(self):
        x=rrf_rank([[2,1,3],[1,3,2]],RRF_K)
        self.assertIn(x[0],(1,2))
        self.assertTrue(len(x)==3)


if __name__=="__main__":
    unittest.main()
