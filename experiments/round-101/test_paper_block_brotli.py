"""R101 original paragraph receipt, block boundary, corruption and amplification tests."""
import tempfile
import unittest
from pathlib import Path

from paper_block_brotli import (
    GROUPS,partition_paper_blocks,base_fts_db,make_grouped_brotli,
    make_individual_brotli,read_receipt,decode_block,paper_id,
    read_probe,evaluate,queries_for_original
)
from qasper_paragraph_retrieval import load_dev


def paper(name,paras,question,gold):
    return {
        "full_text":{"section_name":["Background","Results"],
                     "paragraphs":[paras[:2],paras[2:]]},
        "qas":[{"question":question,"question_id":name+"q",
                "answers":[{"answer":{"evidence":[gold]}}]}],
    }


FIXTURE={
    "paper-A":paper("A",[
        "The original alpha study has a result.",
        "The second alpha experiment had a control.",
        "Alpha analysis is reproduced again.",
        "Alpha final observation has a reported result.",
    ],"Which alpha result?", "The original alpha study has a result."),
    "paper-B":paper("B",[
        "Beta original note is distinct.",
        "Beta another note has one result.",
        "Beta final method reports the outcome.",
        "Beta concluding observation is different.",
    ],"What beta method?", "Beta final method reports the outcome."),
}


class GroupedOriginalEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.docs,self.cases,_=load_dev(FIXTURE)

    def test_group_partition_preserves_all_rowids(self):
        for group in GROUPS:
            blocks=partition_paper_blocks(self.docs,group)
            self.assertEqual([i for chunk in blocks for i in chunk],
                             list(range(1,len(self.docs)+1)))
            self.assertTrue(all(len({paper_id(self.docs[r-1])
                                     for r in block})==1
                                for block in blocks))

    def test_group_one_has_one_source_per_block(self):
        blocks=partition_paper_blocks(self.docs,1)
        self.assertEqual(len(blocks),len(self.docs))
        self.assertTrue(all(len(block)==1 for block in blocks))

    def test_paper_group_never_crosses_article(self):
        blocks=partition_paper_blocks(self.docs,"paper")
        self.assertEqual(len(blocks),len(FIXTURE))
        self.assertEqual([len(block) for block in blocks],[4,4])

    def test_invalid_group_rejected(self):
        with self.assertRaises(ValueError):
            partition_paper_blocks(self.docs,3)

    def test_grouped_receipts_verify_original_unicode_and_offsets(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            base=root/"base.sqlite"
            db=base_fts_db(base,self.docs)
            db.close()
            c=make_grouped_brotli(root/"c.sqlite",base,self.docs,4)
            try:
                for rid,doc in enumerate(self.docs,1):
                    raw=read_receipt(c,rid)
                    self.assertEqual(raw["doc_id"],str(doc["doc_id"]))
                    self.assertEqual(
                        raw["source_bytes"],
                        (doc["title"]+"\n"+" ".join(doc["abstract"])).encode())
                self.assertEqual(c.execute(
                    "SELECT COUNT(*) FROM source_receipts").fetchone()[0],
                    len(self.docs))
            finally:c.close()

    def test_corrupt_block_payload_fails_closed(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            base=root/"base.sqlite"
            db=base_fts_db(base,self.docs)
            db.close()
            c=make_grouped_brotli(root/"c.sqlite",base,self.docs,4)
            try:
                c.execute("UPDATE source_blocks SET compressed=? WHERE block_id=1",
                          (b"wrong data",))
                with self.assertRaises(Exception):
                    read_receipt(c,1)
            finally:c.close()

    def test_receipt_offset_corruption_fails_sha(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            base=root/"base.sqlite"
            db=base_fts_db(base,self.docs)
            db.close()
            c=make_grouped_brotli(root/"c.sqlite",base,self.docs,4)
            try:
                c.execute("UPDATE source_receipts SET byte_offset=byte_offset+1 "
                          "WHERE rowid=1")
                with self.assertRaises(ValueError):
                    read_receipt(c,1)
            finally:c.close()

    def test_swapped_cross_paper_block_id_fails_provenance(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            base=root/"base.sqlite"
            db=base_fts_db(base,self.docs)
            db.close()
            c=make_grouped_brotli(root/"c.sqlite",base,self.docs,4)
            try:
                c.execute("UPDATE source_receipts SET block_id=2 WHERE rowid=1")
                with self.assertRaises(ValueError):
                    read_receipt(c,1)
            finally:c.close()

    def test_query_local_cache_reduces_redundant_block_inflates(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            base=root/"base.sqlite"
            db=base_fts_db(base,self.docs)
            hits=queries_for_original(self.docs,self.cases,db)
            db.close()
            c=make_grouped_brotli(root/"c.sqlite",base,self.docs,"paper")
            try:
                probe=read_probe(c,self.docs,hits,True,10)
                self.assertLessEqual(
                    probe["block_decompressions"],
                    probe["requested_sources_sha_exact"])
                self.assertGreaterEqual(
                    probe["decoded_byte_amplification"],1)
            finally:c.close()

    def test_end_to_end_index_parity_and_all_source_receipts(self):
        r=evaluate(self.docs,self.cases,groups=(1,2,4,"paper"))
        self.assertEqual(r["source_docs"],len(self.docs))
        self.assertEqual(r["queries"],2)
        self.assertEqual(r["individual"]["original_sources_verified"],
                         len(self.docs))
        self.assertTrue(all(x["original_sources_verified"]==len(self.docs)
                            for x in r["groups"]))
        self.assertEqual(
            r["full_original_evidence_recall"]["eligible_text_evidence_questions"],2)


if __name__=="__main__":
    unittest.main()
