"""R98 external paragraph storage-cap and paper-balanced source tests."""
import tempfile
import unittest
from pathlib import Path

from qasper_binding_budget import (
    POLICIES,ARCHITECTURES,prioritization_indices,paper_id,selected_original_order,
    ranges_by_article,subset_cases,paragraph_gold_ids,
    physical_prefix_bytes,largest_prefix,build_db,
    evaluate_subset,paired_seed,
)
from qasper_paragraph_retrieval import load_dev


def fake(pid,paras,question,gold):
    return {
        "full_text":{"section_name":["Paper"],"paragraphs":[paras]},
        "qas":[{"question":question,"question_id":pid+"-q",
                "answers":[{"answer":{"evidence":[gold]}}]}],
    }


PAPERS={
    "a":fake("a",[
        "Alpha wave exists.","A second alpha wave sample.",
        "Alpha was tested in December.","A fourth alpha paragraph."],
        "What about alpha wave?", "Alpha wave exists."),
    "b":fake("b",[
        "Beta wave exists.","A second beta wave sample.",
        "Beta was tested in December.","A fourth beta paragraph."],
        "What about beta wave?", "Beta wave exists."),
    "c":fake("c",[
        "Gamma wave exists.","A second gamma wave sample.",
        "Gamma was tested in December.","A fourth gamma paragraph."],
        "What about gamma wave?", "Gamma wave exists."),
}


class QasperBudgetTests(unittest.TestCase):
    def setUp(self):
        self.docs,self.cases,_=load_dev(PAPERS)
        self.gold=paragraph_gold_ids(self.docs,self.cases)

    def test_paper_id_parses_last_two_components(self):
        self.assertEqual(paper_id({"doc_id":"example|0|3"}),"example")
        self.assertEqual(paper_id({"doc_id":"a|b|1|2"}),"a|b")

    def test_priorities_are_stable_and_complete(self):
        for policy in POLICIES:
            a=prioritization_indices(self.docs,11,policy)
            b=prioritization_indices(self.docs,11,policy)
            self.assertEqual(a,b)
            self.assertEqual(set(a),set(range(len(self.docs))))

    def test_balanced_first_wave_has_one_per_paper(self):
        priority=prioritization_indices(self.docs,11,"paper_balanced_hash")
        picked={paper_id(self.docs[i]) for i in priority[:len(PAPERS)]}
        self.assertEqual(picked,set(PAPERS))

    def test_selected_paragraphs_remain_in_original_paper_contiguous_order(self):
        priority=prioritization_indices(self.docs,37,"global_hash")
        subset=selected_original_order(self.docs,priority,8)
        ranges=ranges_by_article(subset)
        self.assertTrue(ranges)
        cases=subset_cases(self.cases,ranges)
        self.assertEqual(len(cases),len(self.cases))
        for case in cases:
            if case["row_end"]>=case["row_start"]:
                self.assertIn(case["paper"],ranges)

    def test_real_sqlite_prefix_budget_for_both_source_formats(self):
        order=prioritization_indices(self.docs,11,"global_hash")
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)
            for arch in ARCHITECTURES:
                cache={}
                budget=physical_prefix_bytes(p,self.docs,order,6,arch,cache)
                n,actual=largest_prefix(p,self.docs,order,budget,arch,cache)
                self.assertGreaterEqual(n,6)
                self.assertLessEqual(actual,budget)
                if n<len(self.docs):
                    self.assertGreater(physical_prefix_bytes(
                        p,self.docs,order,n+1,arch,cache),budget)

    def test_source_exactness_and_evidence_recall_for_matched_subset(self):
        order=prioritization_indices(self.docs,11,"global_hash")
        subset=selected_original_order(self.docs,order,10)
        outcomes=[]
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)
            for arch in ARCHITECTURES:
                db=build_db(p/(arch+".sqlite"),subset,arch)
                try:
                    result=evaluate_subset(db,subset,self.cases,arch,self.gold)
                    outcomes.append(result)
                finally:
                    db.close()
        self.assertEqual(outcomes[0]["metrics"],outcomes[1]["metrics"])
        self.assertEqual(outcomes[0]["source_checks"][
            "source_receipts_exact_original"],outcomes[1][
            "source_checks"]["source_receipts_exact_original"])

    def test_gold_source_not_retained_is_not_hallucination_judgment(self):
        # Source absence means evidence recall miss, never a model verdict.
        subset=[doc for doc in self.docs if paper_id(doc)!="a"]
        with tempfile.TemporaryDirectory() as root:
            db=build_db(Path(root)/"full.sqlite",subset,"conventional")
            try:
                result=evaluate_subset(
                    db,subset,self.cases,"conventional",self.gold)
                self.assertLess(
                    result["gold_source_available_claims"],len(self.cases))
                self.assertGreaterEqual(result["papers_without_any_source"],1)
            finally:db.close()

    def test_paired_deltas_are_bidirectional(self):
        rows=[]
        for arch,n in (("conventional",6),("compressed",5)):
            rows.append({
                "architecture":arch,"budget":100,"policy":"global_hash",
                "seed":11,"docs_retained":n,"paper_coverage":2,
                "metrics":{"r1":{"hits":n},"r10":{"hits":n}},
                "bits":{"10":[1]*n+[0]*(7-n)},
            })
        output=paired_seed(rows,100,"global_hash",11)
        self.assertEqual(output["paired_r10_losses"],1)
        self.assertEqual(output["paired_r10_wins"],0)

    def test_invalid_policy_and_too_small_budget_fail(self):
        with self.assertRaises(ValueError):
            prioritization_indices(self.docs,11,"nonsense")
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(AssertionError):
                largest_prefix(Path(root),self.docs,list(range(len(self.docs))),
                               1,"conventional",{})


if __name__=="__main__":
    unittest.main()
