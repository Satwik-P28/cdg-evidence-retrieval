"""R94 evidence-conditioned model verdict evaluation, no cross-source label transfer."""
import tempfile
import unittest
from pathlib import Path
from retrieved_verdicts import (
    verdict_from_probabilities,evaluate_scenario,retrieved_entries,
    annotated_gold,make_fts,create_legacy_contentless,
)


CORPUS=[
    {"doc_id":11,"title":"alphaquantum","abstract":["The first observation supports alpha."]},
    {"doc_id":22,"title":"betaplasma","abstract":["A separate observation."]},
    {"doc_id":33,"title":"gammawave","abstract":["The third study contradicts beta."]},
]
CLAIMS=[
    {"id":8,"claim":"alphaquantum observation",
     "evidence":{"11":[{"label":"SUPPORT","sentences":[0]}]}},
    {"id":9,"claim":"betaplasma observation",
     "evidence":{"33":[{"label":"CONTRADICT","sentences":[0]}]}},
]


class RetrievedVerdictTests(unittest.TestCase):
    def test_frozen_support_and_contradiction_policy(self):
        self.assertEqual(verdict_from_probabilities({
            "entailment":.7,"contradiction":.2,"neutral":.1}),"SUPPORT")
        self.assertEqual(verdict_from_probabilities({
            "entailment":.1,"contradiction":.7,"neutral":.2}),"CONTRADICT")

    def test_neutral_is_abstain_not_contradiction(self):
        self.assertEqual(verdict_from_probabilities({
            "entailment":.1,"contradiction":.2,"neutral":.7}),"ABSTAIN")

    def test_missing_or_invalid_probabilities_rejected(self):
        with self.assertRaises(ValueError):
            verdict_from_probabilities({
                "entailment":.5,"contradiction":.5})
        with self.assertRaises(ValueError):
            verdict_from_probabilities({
                "entailment":1.2,"contradiction":-.3,"neutral":.1})

    def test_wrong_retrieved_document_does_not_inherit_gold_label(self):
        cases=annotated_gold(CLAIMS,CORPUS)
        with tempfile.TemporaryDirectory() as root:
            db,_=make_fts(Path(root)/"normal.sqlite",CORPUS,False)
            try:
                rows=retrieved_entries(db,CORPUS,cases,False)
                wrong=next(r for r in rows if r["claim_id"]=="9")
                # Query matches beta but annotated contradicting doc is gamma.
                self.assertEqual(wrong["source_id"],"22")
                self.assertIsNone(wrong["human_label_for_selected_doc"])
            finally:db.close()

    def test_matched_source_conventional_and_compressed_equal(self):
        cases=annotated_gold(CLAIMS,CORPUS)
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)
            full,_=make_fts(p/"normal.sqlite",CORPUS,False)
            compact=create_legacy_contentless(p/"compressed.sqlite",CORPUS)
            try:
                a=retrieved_entries(full,CORPUS,cases,False)
                b=retrieved_entries(compact,CORPUS,cases,True)
                self.assertEqual(a,b)
            finally:full.close();compact.close()

    def test_unannotated_selection_counted_unverified_not_wrong(self):
        rows=[
            {"claim_id":"1","source_id":"11","human_label_for_selected_doc":"SUPPORT"},
            {"claim_id":"2","source_id":"22","human_label_for_selected_doc":None},
            {"claim_id":"3","source_id":"33","human_label_for_selected_doc":"CONTRADICT"},
        ]
        preds={("1","11"):"SUPPORT",("2","22"):"SUPPORT",
               ("3","33"):"ABSTAIN"}
        result,binary=evaluate_scenario(rows,preds,["1","2","3"])
        self.assertEqual(result["correct_annotated_verdict"],1)
        self.assertEqual(result["unannotated_source_retrieved"],1)
        self.assertEqual(result["wrong_annotated_verdict"],0)
        self.assertEqual(result["abstained_on_annotated"],1)
        self.assertEqual(binary,[1,0,0])

    def test_empty_source_does_not_get_model_prediction(self):
        rows=[{"claim_id":"1","source_id":None,
               "human_label_for_selected_doc":None}]
        out,bits=evaluate_scenario(rows,{},["1"])
        self.assertEqual(out["empty_retrieval"],1)
        self.assertEqual(bits,[0])

    def test_failure_on_cohort_misalignment(self):
        rows=[{"claim_id":"1","source_id":None,
               "human_label_for_selected_doc":None}]
        with self.assertRaises(AssertionError):
            evaluate_scenario(rows,{},["2"])


if __name__=="__main__":
    unittest.main()
