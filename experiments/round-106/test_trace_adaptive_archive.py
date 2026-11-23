"""R106 original-source tiered archive, fit/test and transaction safeguards."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from trace_adaptive_archive import (
    POLICIES,split_queries,candidate_order,policy_layouts,original_papers,
    synthetic_edit_plan,live_expected,build_archive,SourceReader,
    source_integrity,edit_source,read_cost,all_query_rankings,
    evaluate,
)
from paper_block_brotli import base_fts_db
from train_only_zstd_dictionary import (
    independently_trained_samples,train_dictionaries
)
from qasper_paragraph_retrieval import load_dev


def sample_paper(pid,n=10,with_qa=True):
    paras=[
        f"The {pid} study examined scientific measurement {i}. "
        +"A real original observation was reconstructed and verified. "*4
        for i in range(n)
    ]
    return {
        "full_text":{"section_name":["Results"],"paragraphs":[paras]},
        "qas":[
            {"question":f"How was original scientific measurement {x} examined?",
             "question_id":pid+"-question"+str(x),
             "answers":[{"answer":{"evidence":[paras[x]]}}]}
            for x in (0,2,4,6)
        ] if with_qa else [],
    }


TRAIN={
    "train-"+str(x):sample_paper("train-"+str(x),40,False)
    for x in range(12)
}
DEV={
    "dev-"+str(x):sample_paper("dev-"+str(x),9,True)
    for x in range(8)
}


class AdaptiveHybridEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs,cls.cases,_=load_dev(DEV)
        cls.groups=original_papers(cls.docs)
        cls.fit,cls.test=split_queries(cls.cases)
        samples,_=independently_trained_samples(TRAIN,450)
        cls.dictionary=train_dictionaries(samples,(65536,))[65536]

    def archive(self,root,policy="all_individual"):
        fts_path=root/"base.sqlite"
        original=base_fts_db(fts_path,self.docs)
        try:
            ranked=all_query_rankings(original,self.cases)
            stats=original.execute(
                "SELECT hex(block) FROM sources_data WHERE id=1"
            ).fetchone()[0]
        finally:original.close()
        fit_rank={x["id"]:ranked[x["id"]] for x in self.fit}
        layouts=policy_layouts(
            self.groups,self.docs,self.fit,fit_rank,policy)
        db,build=build_archive(
            root/"actual.sqlite",fts_path,self.docs,layouts,
            self.dictionary)
        return db,layouts,stats,ranked,build

    def test_query_pseudo_history_split_reproducible_and_disjoint(self):
        a,b=split_queries(self.cases)
        c,d=split_queries(self.cases)
        self.assertEqual(a,c)
        self.assertEqual(b,d)
        self.assertTrue(a)
        self.assertTrue(b)
        self.assertFalse({x["id"] for x in a}&{x["id"] for x in b})

    def test_all_layout_policies_assign_every_original_paper(self):
        fits={x["id"]:[] for x in self.fit}
        for policy in POLICIES:
            result=policy_layouts(self.groups,self.docs,self.fit,fits,policy)
            self.assertEqual(set(result),set(self.groups))
            self.assertTrue(set(result.values()).issubset(
                {"individual","group4","paper"}))

    def test_history_selector_ignores_heldout_question_text_and_gold(self):
        ranks={x["id"]:[x["row_start"]] for x in self.fit}
        a=policy_layouts(
            self.groups,self.docs,self.fit,ranks,"history_25_25")
        # Replacing every held-out question/evidence label cannot enter
        # the fitter, since it receives only fit cases and their ranks.
        new_test=[
            {**x,"claim":"a fabricated heldout test query",
             "gold_rowids":{999999}}
            for x in self.test]
        _=new_test
        b=policy_layouts(
            self.groups,self.docs,self.fit,ranks,"history_25_25")
        self.assertEqual(a,b)

    def test_history_prefers_paper_with_more_fit_source_reads(self):
        fit=[{"id":"q1","paper":"dev-0"}]
        ranked={"q1":[1,2,3,4]}
        scores=candidate_order(
            self.groups,self.docs,fit,ranked,"history")
        self.assertEqual(scores[0],"dev-0")

    def test_real_hybrid_reads_every_original_source_byte(self):
        with tempfile.TemporaryDirectory() as folder:
            db,choices,stats,ranked,_=self.archive(
                Path(folder),"history_25_25")
            try:
                self.assertEqual(
                    source_integrity(db,self.docs,stats),len(self.docs))
                self.assertEqual(db.execute(
                    "SELECT count(*) FROM source_individual").fetchone()[0]+
                    db.execute(
                        "SELECT count(*) FROM source_receipts").fetchone()[0],
                    len(self.docs))
            finally:db.close()

    def test_no_cross_paper_block_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            db,choices,stats,ranked,_=self.archive(
                Path(folder),"all_paper")
            try:
                db.execute(
                    "UPDATE source_receipts SET block_id=2 WHERE rowid=1")
                with self.assertRaises(ValueError):
                    SourceReader(db).read(1)
            finally:db.close()

    def test_tampered_stored_dictionary_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            db,choices,stats,ranked,_=self.archive(
                Path(folder),"all_individual")
            try:
                db.execute(
                    "UPDATE source_dictionaries SET sha256=? WHERE dict_id=1",
                    (b"\xff"*32,))
                with self.assertRaises(ValueError):
                    SourceReader(db)
            finally:db.close()

    def test_real_hybrid_transaction_rollback_both_layouts(self):
        for layout in ("all_individual","all_paper"):
            with tempfile.TemporaryDirectory() as folder:
                db,_,stats,_,_=self.archive(Path(folder),layout)
                try:
                    before=SourceReader(db).read(1)["source_bytes"]
                    for fault in ("after_fts","after_source"):
                        with self.assertRaises(RuntimeError):
                            edit_source(db,SourceReader(db),1,
                                str(self.docs[0]["doc_id"]),
                                "Results",["changed source rollback"],fault=fault)
                        self.assertEqual(
                            SourceReader(db).read(1)["source_bytes"],before)
                        self.assertFalse(db.in_transaction)
                    self.assertEqual(
                        db.execute("SELECT hex(block) FROM sources_data "
                                   "WHERE id=1").fetchone()[0],stats)
                finally:db.close()

    def test_revision_updates_following_offsets_not_other_papers(self):
        with tempfile.TemporaryDirectory() as folder:
            db,_,_,_,_=self.archive(Path(folder),"all_paper")
            try:
                before=[
                    SourceReader(db).read(i)["source_bytes"]
                    for i in range(1,len(self.docs)+1)]
                edit_source(db,SourceReader(db),1,
                    str(self.docs[0]["doc_id"]),"Results",
                    ["new large science observations "*40])
                self.assertNotEqual(
                    SourceReader(db).read(1)["source_bytes"],before[0])
                for rid in range(2,len(self.docs)+1):
                    self.assertEqual(
                        SourceReader(db).read(rid)["source_bytes"],
                        before[rid-1])
            finally:db.close()

    def test_individual_source_layout_has_one_to_one_decode(self):
        with tempfile.TemporaryDirectory() as folder:
            db,_,_,ranks,_=self.archive(
                Path(folder),"all_individual")
            try:
                result=read_cost(db,self.docs,self.test,ranks,10)
                self.assertEqual(result["decoded_byte_amplification"],1.0)
            finally:db.close()

    def test_holdout_query_does_not_change_gold_recall_under_layouts(self):
        with tempfile.TemporaryDirectory() as folder:
            db,_,_,ranks,_=self.archive(
                Path(folder),"history_25_25")
            try:
                original=read_cost(db,self.docs,self.test,ranks,10)
                self.assertGreater(original["source_receipts_verified"],0)
                self.assertGreaterEqual(
                    original["decoded_byte_amplification"],1.0)
            finally:db.close()

    def test_synthetic_revisions_do_not_mutate_original_doc_fixture(self):
        original=self.docs[0]["abstract"][0]
        plan=synthetic_edit_plan(self.docs,18)
        changed=live_expected(self.docs,plan)
        self.assertEqual(self.docs[0]["abstract"][0],original)
        self.assertEqual(len(plan),18)
        self.assertEqual(len(changed),len(self.docs))

    def test_complete_small_corpus_archive_control_and_revisions(self):
        # Real SQLite physical source bytes and WAL, 4 independent arms.
        result=evaluate(
            TRAIN,DEV,
            policies=("all_individual","all_paper",
                      "history_25_25","hash_25_25"),
            edit_count=10)
        self.assertEqual(len(result["archives"]),4)
        self.assertEqual(result["original_corpus"]["questions"],32)
        for row in result["archives"]:
            self.assertEqual(row["original_source_readbacks"],len(self.docs))
            self.assertEqual(row["identical_original_question_ranks"],32)
            self.assertEqual(
                row["synthetic_heldout_edit_stress"][
                    "matched_conventional_post_edit_top10"],32)
            self.assertGreater(
                row["synthetic_heldout_edit_stress"]["wal_appended_bytes"],0)

    def test_invalid_source_layout_policy_fails_closed(self):
        with self.assertRaises(ValueError):
            policy_layouts(self.groups,self.docs,self.fit,{},"made_up")


if __name__=="__main__":
    unittest.main()
