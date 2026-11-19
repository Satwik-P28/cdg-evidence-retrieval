"""R97 QASPER scoped original-source retrieval and gold-evidence tests."""
import tempfile
import unittest
from pathlib import Path

from qasper_paragraph_retrieval import (
    load_dev,paper_rank,scoped_rankings,gold_recall,
    evaluate,bootstrap_eligible,make_fts,create_legacy_contentless
)


def paper(title,paras,question,gold,ident):
    return {
        "title":title,
        "full_text":{"section_name":["Body"],
                     "paragraphs":[paras]},
        "qas":[{
            "question":question,"question_id":ident,
            "answers":[{"answer":{"evidence":gold}}],
        }],
    }


PAPERS={
    "paper1":paper(
        "Alpha Study",
        ["alphaquartz was measured in three trials.",
         "Another observation on beta minerals."],
        "How was alphaquartz measured?",
        ["alphaquartz was measured in three trials."],"q1"),
    "paper2":paper(
        "Gamma Study",
        ["alphaquartz appears in a different paper.",
         "gammawave supports an unrelated sample."],
        "How is gammawave used?",
        ["gammawave supports an unrelated sample."],"q2"),
}


class QasperParagraphRetrievalTests(unittest.TestCase):
    def test_flattening_preserves_all_paragraphs_and_paper_scopes(self):
        docs,cases,counts=load_dev(PAPERS)
        self.assertEqual(len(docs),4)
        self.assertEqual(len(cases),2)
        self.assertEqual((cases[0]["row_start"],cases[0]["row_end"]),(1,2))
        self.assertEqual((cases[1]["row_start"],cases[1]["row_end"]),(3,4))
        self.assertEqual(counts["questions_with_at_least_one_exact_text_evidence"],2)

    def test_paper_scope_cannot_return_strong_other_paper_hit(self):
        docs,cases,_=load_dev(PAPERS)
        with tempfile.TemporaryDirectory() as root:
            conn,_=make_fts(Path(root)/"f.sqlite",docs,False)
            try:
                self.assertTrue(all(x in (1,2) for x in paper_rank(
                    conn,"alphaquartz",1,2)))
                self.assertTrue(all(x in (3,4) for x in paper_rank(
                    conn,"alphaquartz",3,4)))
            finally:conn.close()

    def test_matched_ranks_and_source_bytes_exact_in_two_architectures(self):
        result=evaluate(PAPERS)
        self.assertEqual(result["exact_rankings_all_questions"],2)
        self.assertEqual(result["documents_indexed"],4)
        self.assertEqual(result["static_sqlite_fts_integrity"]["compressed"],"ok")
        self.assertEqual(
            result["human_evidence_paragraph_recall"]["eligible_text_evidence_questions"],2)

    def test_complete_unannotated_evidence_is_excluded_not_negative(self):
        other={"paper3":paper("No evidence",
            ["an open domain snippet"],"What happened?",[],"q3")}
        docs,cases,_=load_dev({**PAPERS,**other})
        self.assertEqual(len(cases),3)
        with tempfile.TemporaryDirectory() as root:
            conn,_=make_fts(Path(root)/"f.sqlite",docs,False)
            try:
                ranks,_=scoped_rankings(conn,docs,cases,False)
                result=gold_recall(cases,ranks)
                self.assertEqual(result["eligible_text_evidence_questions"],2)
                self.assertEqual(result["excluded_no_exact_text_evidence"],1)
            finally:conn.close()

    def test_unmatched_figure_evidence_not_forced_onto_paragraph(self):
        p={"x":paper("Figures",["some unrelated text."],
                     "What figure shows? ",["FLOAT SELECTED fig1"],"q")}
        docs,cases,meta=load_dev(p)
        self.assertEqual(meta["figure_table_references"],1)
        self.assertEqual(len(cases[0]["gold_rowids"]),0)

    def test_whitespace_matched_gold_preserves_annotated_paragraph_id(self):
        p={"x":paper("Whitespace",["This  exact\n paragraph."],
                     "exact paragraph",["This exact paragraph."],"q")}
        docs,cases,meta=load_dev(p)
        self.assertEqual(cases[0]["gold_rowids"],{1})

    def test_rank_empty_query_handled_as_no_hits(self):
        docs,cases,_=load_dev(PAPERS)
        with tempfile.TemporaryDirectory() as root:
            conn,_=make_fts(Path(root)/"f.sqlite",docs,False)
            try:
                self.assertEqual(paper_rank(conn,"and or",1,2),[])
                self.assertEqual(paper_rank(conn,"alphaquartz",2,1),[])
            finally:conn.close()

    def test_evidence_remains_scoped_to_own_paper(self):
        docs,cases,_=load_dev(PAPERS)
        for case in cases:
            self.assertTrue(all(case["row_start"]<=rid<=case["row_end"]
                                for rid in case["gold_rowids"]))

    def test_source_ranking_parity_enforced(self):
        docs,cases,_=load_dev(PAPERS)
        with tempfile.TemporaryDirectory() as root:
            r=Path(root)
            f,_=make_fts(r/"f.sqlite",docs,False)
            c=create_legacy_contentless(r/"c.sqlite",docs)
            try:
                a,_=scoped_rankings(f,docs,cases,False)
                b,_=scoped_rankings(c,docs,cases,True)
                self.assertEqual(a,b)
                self.assertEqual(
                    bootstrap_eligible(cases,a,b,10)["mismatched_ranks"],0)
            finally:f.close();c.close()


if __name__=="__main__":
    unittest.main()
