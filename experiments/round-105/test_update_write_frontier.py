"""R105 actual WAL and original source byte-bound revision frontier guards."""
import tempfile
import unittest
from pathlib import Path

from update_write_frontier import (
    deterministic_edit_plan,expected_corpus,benchmark_archives,
    update_individual,individual_base,individual_variant,
    configure_wal,run_edits
)
from train_only_zstd_dictionary import (
    independently_trained_samples,train_dictionaries
)
from qasper_paragraph_retrieval import load_dev


def paper(pid,n,questions=True):
    paras=[
        "Scientific method and independent original measurement "+str(j)
        +" in "+pid+", repeated evidence for an existing result. "*4
        for j in range(n)]
    return {
        "full_text":{"section_name":["Methodology"],"paragraphs":[paras]},
        "qas":[{"question":"Which original scientific method?",
                "question_id":pid+"-q",
                "answers":[{"answer":{"evidence":[paras[0]]}}]}]
                if questions else [],
    }


TRAIN={"train-"+str(i):paper("train-"+str(i),30,False)
       for i in range(12)}
DEV={"dev-A":paper("dev-A",8),"dev-B":paper("dev-B",9)}


class WriteFrontierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs,cls.cases,_=load_dev(DEV)
        cls.small_result=benchmark_archives(
            TRAIN,DEV,groups=(1,4,"paper"),
            group_codecs=("brotli5","zstd9-dictionary"),
            indiv_codecs=("brotli5","zstd9_dict65536"),
            n_edits=12)

    def test_mutation_plan_is_deterministic(self):
        x=deterministic_edit_plan(self.docs,20)
        y=deterministic_edit_plan(self.docs,20)
        self.assertEqual(x,y)
        self.assertEqual(len(x),20)
        self.assertTrue(all(1<=row[0]<=len(self.docs) for row in x))

    def test_mutations_do_not_alter_original_source_fixture(self):
        before=self.docs[0]["abstract"][0]
        updated=expected_corpus(
            self.docs,deterministic_edit_plan(self.docs,20))
        self.assertEqual(self.docs[0]["abstract"][0],before)
        self.assertNotEqual(updated[0]["abstract"][0],before)

    def test_predeclared_full_archive_arm_count(self):
        self.assertEqual(len(self.small_result["arms"]),8)
        self.assertEqual(
            sum(x["source_layout"]=="individual"
                for x in self.small_result["arms"]),2)

    def test_real_wal_bytes_charged_for_every_arm(self):
        self.assertTrue(all(x["WAL_file_peak_bytes"]>0
                            for x in self.small_result["arms"]))
        self.assertTrue(all(x["WAL_bytes_appended_sum"]>0
                            for x in self.small_result["arms"]))
        self.assertTrue(all(x["source_revision_ms"]["count"]==12
                            for x in self.small_result["arms"]))

    def test_source_reencoded_bytes_and_byte_ratio_finite(self):
        self.assertTrue(all(x["source_reencoded_BLOB_bytes_sum"]>0
                            for x in self.small_result["arms"]))
        self.assertTrue(all(
            x["compressed_BLOB_rewrite_to_changed_original_ratio"]>0
            for x in self.small_result["arms"]))

    def test_all_archives_restore_original_source_and_FTS_after_edits(self):
        self.assertTrue(all(x["verified_source_receipts"]==len(self.docs)
                            for x in self.small_result["arms"]))
        self.assertTrue(all(x["identical_top10_question_rankings"]==2
                            for x in self.small_result["arms"]))
        self.assertTrue(all(x["unchanged_FTS_global_stats"]
                            for x in self.small_result["arms"]))

    def test_original_dictionary_article_overlap_blocks_benchmark(self):
        with self.assertRaises(AssertionError):
            benchmark_archives(
                TRAIN,{"train-0":TRAIN["train-0"]},
                groups=(1,),group_codecs=("brotli5",),
                indiv_codecs=("brotli5",),n_edits=1)

    def test_strong_individual_source_reference_has_real_size(self):
        chosen=[r for r in self.small_result["arms"]
                if r["source_layout"]=="individual"]
        self.assertTrue(all(r["initial_static_archive_bytes"]>0
                            and r["final_compacted_archive_bytes"]>0
                            for r in chosen))

    def test_individual_identity_mismatch_rejected_with_rollback(self):
        samples,_=independently_trained_samples(TRAIN,200)
        dictionaries=train_dictionaries(samples,(65536,))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            base=root/"base.sqlite"
            conn=individual_base(base,self.docs);conn.close()
            db,_=individual_variant(
                root/"source.sqlite",base,self.docs,
                "zstd9_dict65536",dictionaries)
            try:
                configure_wal(db)
                with self.assertRaises((ValueError,KeyError)):
                    update_individual(
                        db,1,"not-original-source","Methodology",
                        ["corrupted source identity"])
                self.assertFalse(db.in_transaction)
            finally:db.close()

    def test_malformed_individual_source_title_rejected(self):
        samples,_=independently_trained_samples(TRAIN,200)
        dictionaries=train_dictionaries(samples,(65536,))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            base=root/"base.sqlite"
            c=individual_base(base,self.docs);c.close()
            db,_=individual_variant(
                root/"source.sqlite",base,self.docs,"brotli5",dictionaries)
            try:
                with self.assertRaises(ValueError):
                    update_individual(
                        db,1,str(self.docs[0]["doc_id"]),
                        "title\nboundary",["invalid title"])
            finally:db.close()

    def test_same_number_of_source_edits_for_all_codecs(self):
        self.assertEqual(
            {x["revisions"] for x in self.small_result["arms"]},{12})


if __name__=="__main__":
    unittest.main()
