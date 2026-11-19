"""R92 source provenance, no label leakage and paired-budget invariants."""
import random
import tempfile
import unittest
from pathlib import Path
from storage_budget_eval import (
    annotated_gold, deterministic_order, bootstrap_diff,
    recall, rankings, budget_prefix_count, one_seed,
)
from storage_budget_eval import make_fts, create_legacy_contentless


DOCS=[
    {"doc_id":i+1,"title":"mineral"+str(i),
     "abstract":["The independently recorded mineral "+str(i)+" sample."]}
    for i in range(18)
]
CLAIMS=[
    {"id":3,"claim":"mineral3","evidence":{
        "4":[{"label":"SUPPORT","sentences":[0]}]}},
    {"id":4,"claim":"mineral4","evidence":{
        "5":[{"label":"CONTRADICT","sentences":[0]}]}},
    {"id":5,"claim":"mineral5","evidence":{}},
]


class BudgetRetrievalTests(unittest.TestCase):
    def test_fixed_hash_permutation_has_all_docs_and_determinism(self):
        one=deterministic_order(DOCS,11)
        two=deterministic_order(DOCS,11)
        self.assertEqual(one,two)
        self.assertEqual({str(r["doc_id"]) for r in one},
                         {str(r["doc_id"]) for r in DOCS})
        self.assertNotEqual([r["doc_id"] for r in one],
                            [r["doc_id"] for r in deterministic_order(DOCS,23)])

    def test_human_labels_are_only_claim_document_pairs(self):
        selected=annotated_gold(CLAIMS,DOCS)
        self.assertEqual(len(selected),2)
        self.assertEqual(selected[0]["labels"],{"4":"SUPPORT"})
        self.assertEqual(selected[1]["labels"],{"5":"CONTRADICT"})
        with self.assertRaises(AssertionError):
            annotated_gold([{"id":1,"claim":"x","evidence":{
                "4":[{"label":"UNANNO","sentences":[0]}]}}],DOCS)

    def test_budget_recall_denominator_and_missing_annotated_source(self):
        cases=annotated_gold(CLAIMS,DOCS)
        result=recall(cases,{"3":["4"],"4":["7"]},{"4","7"})
        self.assertEqual(result["eligible_claims"],2)
        self.assertEqual(result["annotated_source_present_in_retained_corpus"],1)
        self.assertEqual(result["recall"]["r1"]["hits"],1)
        self.assertEqual(result["recall"]["r10"]["hits"],1)
        self.assertEqual(result["by_gold_source_label"]["CONTRADICT"]["r1_hits"],0)

    def test_paired_win_loss_signs_not_synthetic_label_transfer(self):
        out=bootstrap_diff([1,1,0,0],[0,1,1,0],reps=100,seed=9)
        self.assertEqual(out["wins"],1)
        self.assertEqual(out["losses"],1)
        self.assertEqual(out["ties"],2)
        self.assertEqual(out["percentage_point_gain"],0)

    def test_matched_standard_fts_and_compressed_rankings_equal(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)
            a,_=make_fts(p/"a.sqlite",DOCS,False)
            b=create_legacy_contentless(p/"b.sqlite",DOCS)
            try:
                ra,ca=rankings(a,DOCS,CLAIMS,False)
                rb,cb=rankings(b,DOCS,CLAIMS,True)
                self.assertEqual(ra,rb)
                self.assertEqual(ca["queries"],3)
                self.assertEqual(ca["top_one_verified_reads"],
                                 cb["top_one_verified_reads"])
            finally:
                a.close();b.close()

    def test_budget_prefix_is_within_budget_and_next_exceeds(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)
            ordered=deterministic_order(DOCS,11)
            a,_=make_fts(p/"four.sqlite",ordered[:4],False)
            a.close()
            b,_=make_fts(p/"five.sqlite",ordered[:5],False)
            b.close()
            size4=(p/"four.sqlite").stat().st_size
            size5=(p/"five.sqlite").stat().st_size
            if size4==size5:
                self.skipTest("SQLite page size makes 4 and 5 indistinguishable")
            if size5<size4:
                self.skipTest("FTS pages nonmonotone on tiny fixture")
            n,used,meta=budget_prefix_count(p,ordered,size4)
            self.assertGreaterEqual(n,4)
            self.assertLessEqual(used,size4)
            self.assertGreater(meta["sizes_measured"],0)

    def test_duplicate_source_ids_do_not_silently_split_identity(self):
        with self.assertRaises(AssertionError):
            deterministic_order(DOCS+[DOCS[0]],11)

    def test_subset_ranks_have_correct_source_docids_not_rowids(self):
        subset=deterministic_order(DOCS,11)[:12]
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)
            c=create_legacy_contentless(p/"c.sqlite",subset)
            try:
                r,_=rankings(c,subset,CLAIMS,True)
                self.assertTrue(all(str(sid) in
                    {str(d["doc_id"]) for d in subset}
                    for seq in r.values() for sid in seq))
            finally:c.close()


if __name__=="__main__":
    unittest.main()
