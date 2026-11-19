"""R103 block×dictionary independent article and SHA receipt regression suite."""
import tempfile
import unittest
from pathlib import Path

from joint_group_dictionary import (
    GROUPS,VARIANTS,group_variant,GroupSourceReader,verify_all_originals,
    probe,pareto_frontier,evaluate
)
from paper_block_brotli import base_fts_db,make_grouped_brotli,queries_for_original
from train_only_zstd_dictionary import (
    independently_trained_samples,train_dictionaries
)
from qasper_paragraph_retrieval import load_dev


def paper(pid,count,with_question=True):
    paras=[
        "Observed independent experimental result "+str(i)
        +" on "+pid+" with scientific evidence " + (
            "and repeated verification of the original source calculation. "*4
        ) for i in range(count)
    ]
    return {
        "full_text":{"section_name":["Introduction"],"paragraphs":[paras]},
        "qas":[{
            "question":"What experimental result was observed?",
            "question_id":pid+"q",
            "answers":[{"answer":{"evidence":[paras[0]]}}],
        }] if with_question else [],
    }


TRAIN={
    "train-"+str(i):paper("train-"+str(i),40,False)
    for i in range(12)
}
DEV={
    "dev-A":paper("dev-A",5),
    "dev-B":paper("dev-B",6),
}


class GroupDictionaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs,cls.cases,_=load_dev(DEV)
        samples,_=independently_trained_samples(TRAIN,400)
        cls.dictionary=train_dictionaries(samples,(65536,))[65536]

    def grouped_fixture(self,root,group=2):
        base=root/"base.sqlite"
        db=base_fts_db(base,self.docs)
        db.close()
        source=root/"blocks.sqlite"
        groupdb=make_grouped_brotli(source,base,self.docs,group)
        groupdb.close()
        return source

    def test_both_codecs_verified_on_independent_original_sources(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            base=self.grouped_fixture(root)
            for codec in VARIANTS:
                conn,_=group_variant(
                    root/(codec+".sqlite"),base,codec,self.dictionary)
                try:
                    r=GroupSourceReader(conn)
                    self.assertEqual(
                        verify_all_originals(r,self.docs),len(self.docs))
                finally:conn.close()

    def test_dictionary_metadata_charged_inside_sqlite(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            base=self.grouped_fixture(root)
            conn,metrics=group_variant(
                root/"zstd.sqlite",base,"zstd3-dictionary",self.dictionary)
            try:
                self.assertEqual(
                    metrics["dictionary_charged_bytes"],
                    len(self.dictionary["raw"]))
                self.assertEqual(conn.execute(
                    "SELECT SUM(length(payload)) FROM source_dictionaries"
                    ).fetchone()[0],len(self.dictionary["raw"]))
            finally:conn.close()

    def test_unknown_variant_rejected(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            base=self.grouped_fixture(root)
            with self.assertRaises(ValueError):
                group_variant(
                    root/"bad.sqlite",base,"invented-new-codec",self.dictionary)

    def test_source_receipt_wrong_offset_is_rejected(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            base=self.grouped_fixture(root)
            conn,_=group_variant(
                root/"zstd.sqlite",base,"zstd9-dictionary",self.dictionary)
            try:
                conn.execute("UPDATE source_receipts SET byte_offset=byte_offset+1 "
                             "WHERE rowid=1")
                with self.assertRaises(ValueError):
                    GroupSourceReader(conn).read(1)
            finally:conn.close()

    def test_corrupted_dictionary_is_rejected(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            base=self.grouped_fixture(root)
            conn,_=group_variant(
                root/"zstd.sqlite",base,"zstd9-dictionary",self.dictionary)
            try:
                conn.execute(
                    "UPDATE source_dictionaries SET payload=? WHERE dict_id=1",
                    (b"invalid!",))
                with self.assertRaises(ValueError):
                    GroupSourceReader(conn)
            finally:conn.close()

    def test_wrong_paper_receipt_block_is_rejected(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            base=self.grouped_fixture(root,group="paper")
            conn,_=group_variant(
                root/"zstd.sqlite",base,"zstd3-dictionary",self.dictionary)
            try:
                conn.execute("UPDATE source_receipts SET block_id=2 WHERE rowid=1")
                with self.assertRaises(ValueError):
                    GroupSourceReader(conn).read(1)
            finally:conn.close()

    def test_corrupted_block_digest_is_rejected(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            base=self.grouped_fixture(root)
            conn,_=group_variant(
                root/"zstd.sqlite",base,"zstd9-dictionary",self.dictionary)
            try:
                conn.execute(
                    "UPDATE source_blocks SET sha256=? WHERE block_id=1",
                    (b"\xff"*32,))
                with self.assertRaises(ValueError):
                    GroupSourceReader(conn).read(1)
            finally:conn.close()

    def test_per_query_cache_reduces_duplicate_inflation(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            base=root/"base.sqlite"
            raw=base_fts_db(base,self.docs)
            ranks=queries_for_original(self.docs,self.cases,raw)
            raw.close()
            grouped=root/"blocks.sqlite"
            c=make_grouped_brotli(grouped,base,self.docs,"paper")
            c.close()
            conn,_=group_variant(
                root/"zstd.sqlite",grouped,"zstd3-dictionary",self.dictionary)
            try:
                metrics=probe(GroupSourceReader(conn),self.docs,ranks,10)
                self.assertLessEqual(
                    metrics["distinct_block_inflations"],
                    len(self.cases))
                self.assertGreaterEqual(
                    metrics["decode_byte_amplification"],1)
            finally:conn.close()

    def test_pareto_drops_strictly_dominated_source(self):
        data=[
            {"group":1,"variant":"A","source_plus_fts_sqlite_bytes":100,
             "top1":{"decode_byte_amplification":1.0},
             "top10":{"decode_byte_amplification":1.0}},
            {"group":4,"variant":"B","source_plus_fts_sqlite_bytes":90,
             "top1":{"decode_byte_amplification":2.0},
             "top10":{"decode_byte_amplification":1.4}},
            {"group":4,"variant":"C","source_plus_fts_sqlite_bytes":95,
             "top1":{"decode_byte_amplification":3.0},
             "top10":{"decode_byte_amplification":1.6}},
        ]
        frontier=pareto_frontier(data)
        self.assertEqual({x["codec"] for x in frontier},{"A","B"})

    def test_small_end_to_end_matches_human_evidence_and_full_rankings(self):
        result=evaluate(
            TRAIN,DEV,groups=(1,2,4,"paper"),
            variants=("brotli5","zstd3-dictionary"))
        self.assertEqual(result["source_docs"],len(self.docs))
        self.assertEqual(result["questions"],2)
        self.assertEqual(len(result["grouped_variants"]),8)
        self.assertTrue(all(x["question_rankings_exact"]==2
                            for x in result["grouped_variants"]))
        self.assertEqual(
            result["same_original_gold_paragraph_recall"][
                "eligible_text_evidence_questions"],2)

    def test_overlap_of_dictionary_training_and_dev_papers_rejected(self):
        with self.assertRaises(AssertionError):
            evaluate(TRAIN,{"train-0":TRAIN["train-0"]},
                     groups=(1,),variants=("brotli5",))


if __name__=="__main__":
    unittest.main()
