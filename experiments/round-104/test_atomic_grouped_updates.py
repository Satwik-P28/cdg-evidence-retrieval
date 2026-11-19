"""R104 grouped original source atomic revisions, kill and WAL snapshot tests."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from atomic_grouped_updates import (
    FAULTS,create_test_archive,fts_stats,update_grouped,verified_source,
    retrieve_snapshot,subprocess_crash_probe,conventional_source_update
)
from qasper_paragraph_retrieval import load_dev,paper_rank
from contentless_cas import make_fts
from train_only_zstd_dictionary import (
    independently_trained_samples,train_dictionaries
)
from joint_group_dictionary import GroupSourceReader


def article(pid,paragraphs):
    return {
        "full_text":{"section_name":["Methods"],
                     "paragraphs":[paragraphs]},
        "qas":[{
            "question":"Which unique measurement?",
            "question_id":pid+"q",
            "answers":[{"answer":{"evidence":[paragraphs[0]]}}],
        }],
    }


TRAIN={
    "train-"+str(i):article(
        "train-"+str(i),[
            "Research evidence repeated to improve independent sample "
            +str(j)+" with experimental results "
            +("and verified source text for all users. "*4)
            for j in range(30)])
    for i in range(12)
}
DEV={
    "a-paper":article("a-paper",[
        "unique_alpha_"+str(i)+" records measurement and scientific evidence."
        for i in range(8)
    ]),
    "b-paper":article("b-paper",[
        "unique_beta_"+str(i)+" records a distinct laboratory observation."
        for i in range(8)
    ]),
}


class GroupedAtomicUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs,cls.cases,_=load_dev(DEV)
        samples,_=independently_trained_samples(TRAIN,320)
        cls.dictionary=train_dictionaries(samples,(65536,))[65536]

    def fixture(self,folder,group=4,variant="zstd9-dictionary"):
        return create_test_archive(
            folder/"original.sqlite",self.docs,group=group,
            variant=variant,dictionary=self.dictionary)

    def test_update_changes_only_target_source_and_offsets(self):
        with tempfile.TemporaryDirectory() as scratch:
            db=self.fixture(Path(scratch))
            try:
                originals=[
                    verified_source(db,i)["source_bytes"]
                    for i in range(1,len(self.docs)+1)]
                doc_id=str(self.docs[0]["doc_id"])
                result=update_grouped(
                    db,1,doc_id,"Methods",
                    ["the new, longer unique_alpha_0 original evidence "
                     "with an additional observed scientific result."])
                self.assertEqual(result["source_generation"],2)
                self.assertEqual(result["block_generation"],2)
                self.assertNotEqual(
                    verified_source(db,1)["source_bytes"],originals[0])
                for i in range(2,len(self.docs)+1):
                    self.assertEqual(
                        verified_source(db,i)["source_bytes"],originals[i-1])
            finally:db.close()

    def test_repeated_hot_source_edits_preserve_index_stats(self):
        with tempfile.TemporaryDirectory() as scratch:
            p=Path(scratch)
            grouped=self.fixture(p)
            ordinary,_=make_fts(p/"ordinary.sqlite",self.docs,False)
            try:
                for i in range(50):
                    txt=("unique_alpha_0 updated scientific source "+str(i)
                         +" more observations "*((i%4)+1))
                    update_grouped(
                        grouped,1,str(self.docs[0]["doc_id"]),"Methods",[txt])
                    conventional_source_update(
                        ordinary,1,"Methods",[txt])
                self.assertEqual(fts_stats(grouped),fts_stats(ordinary))
                for query in ("unique_alpha_0","scientific observations",
                              "updated evidence"):
                    self.assertEqual(
                        paper_rank(grouped,query,1,8,10),
                        paper_rank(ordinary,query,1,8,10))
                self.assertEqual(grouped.execute(
                    "SELECT generation FROM source_receipts WHERE rowid=1"
                    ).fetchone()[0],51)
            finally:grouped.close();ordinary.close()

    def test_each_precommit_fault_rolls_back_original_source(self):
        with tempfile.TemporaryDirectory() as scratch:
            db=self.fixture(Path(scratch))
            try:
                before=verified_source(db,1)["source_bytes"]
                index=fts_stats(db)
                for stage in FAULTS[:-1]:
                    with self.assertRaises(RuntimeError):
                        update_grouped(
                            db,1,str(self.docs[0]["doc_id"]),
                            "Methods",["mutated for failure "+stage],
                            fault=stage)
                    self.assertEqual(
                        verified_source(db,1)["source_bytes"],before)
                    self.assertEqual(fts_stats(db),index)
                    self.assertEqual(db.execute(
                        "SELECT generation FROM source_receipts WHERE rowid=1"
                        ).fetchone()[0],1)
            finally:db.close()

    def test_exception_after_commit_does_not_roll_back_committed_source(self):
        with tempfile.TemporaryDirectory() as scratch:
            db=self.fixture(Path(scratch))
            try:
                with self.assertRaises(RuntimeError):
                    update_grouped(
                        db,1,str(self.docs[0]["doc_id"]),
                        "Methods",["source visible after COMMIT"],
                        fault="after_commit")
                self.assertEqual(
                    verified_source(db,1)["source_bytes"],
                    b"Methods\nsource visible after COMMIT")
                self.assertEqual(db.execute(
                    "SELECT generation FROM source_receipts WHERE rowid=1"
                    ).fetchone()[0],2)
            finally:db.close()

    def test_wrong_source_identity_fails_without_index_change(self):
        with tempfile.TemporaryDirectory() as scratch:
            db=self.fixture(Path(scratch))
            try:
                before=fts_stats(db)
                with self.assertRaises(KeyError):
                    update_grouped(
                        db,1,"foreign-source","Methods",["some new data"])
                self.assertEqual(fts_stats(db),before)
            finally:db.close()

    def test_malformed_new_title_rejected_without_begin(self):
        with tempfile.TemporaryDirectory() as scratch:
            db=self.fixture(Path(scratch))
            try:
                with self.assertRaises(ValueError):
                    update_grouped(
                        db,1,str(self.docs[0]["doc_id"]),
                        "broken\nheader",["text"])
                self.assertFalse(db.in_transaction)
            finally:db.close()

    def test_source_sha_tampering_blocks_revision(self):
        with tempfile.TemporaryDirectory() as scratch:
            db=self.fixture(Path(scratch))
            try:
                db.execute(
                    "UPDATE source_receipts SET sha256=? WHERE rowid=1",
                    (b"\xff"*32,))
                with self.assertRaises(ValueError):
                    update_grouped(
                        db,1,str(self.docs[0]["doc_id"]),
                        "Methods",["malicious edit"])
                self.assertFalse(db.in_transaction)
            finally:db.close()

    def test_wal_snapshot_keeps_old_content_between_rank_and_receipt(self):
        with tempfile.TemporaryDirectory() as scratch:
            p=Path(scratch)
            source=self.fixture(p)
            source.execute("PRAGMA journal_mode=WAL")
            source.close()
            reader=sqlite3.connect(str(p/"original.sqlite"),isolation_level=None)
            writer=sqlite3.connect(str(p/"original.sqlite"),isolation_level=None)
            try:
                old=GroupSourceReader(reader).read(1)["source_bytes"]
                updated=b"Methods\nunique_alpha_0 edited science after commit"
                def interleave():
                    update_grouped(
                        writer,1,str(self.docs[0]["doc_id"]),
                        "Methods",["unique_alpha_0 edited science after commit"])
                receipts=retrieve_snapshot(
                    reader,"unique_alpha_0",1,8,k=10,
                    interleave=interleave)
                target=[r["source_bytes"] for rid,r in receipts if rid==1]
                self.assertEqual(target,[old])
                self.assertEqual(
                    GroupSourceReader(reader).read(1)["source_bytes"],updated)
            finally:reader.close();writer.close()

    def test_ten_real_kill_process_cases(self):
        outcomes=subprocess_crash_probe(
            self.docs[:8],self.dictionary)
        self.assertEqual(len(outcomes),10)
        self.assertEqual(sum(x["committed_source_visible"]
                             for x in outcomes),2)
        self.assertEqual(set(x["mode"] for x in outcomes),
                         {"DELETE","WAL"})

    def test_individual_brotli_archive_update_uses_same_transaction_path(self):
        with tempfile.TemporaryDirectory() as scratch:
            db=self.fixture(Path(scratch),variant="brotli5")
            try:
                result=update_grouped(
                    db,1,str(self.docs[0]["doc_id"]),"Methods",
                    ["unique_alpha_0 from independent Brotli block revision"])
                self.assertEqual(result["source_generation"],2)
                self.assertTrue(
                    verified_source(db,1)["source_bytes"].endswith(
                        b"Brotli block revision"))
            finally:db.close()

    def test_different_block_offsets_not_modified_by_local_revision(self):
        with tempfile.TemporaryDirectory() as scratch:
            db=self.fixture(Path(scratch),group=4)
            try:
                before=db.execute(
                    "SELECT byte_offset FROM source_receipts WHERE rowid=5"
                ).fetchone()[0]
                update_grouped(
                    db,1,str(self.docs[0]["doc_id"]),
                    "Methods",["replaced long original evidence"*20])
                after=db.execute(
                    "SELECT byte_offset FROM source_receipts WHERE rowid=5"
                ).fetchone()[0]
                self.assertEqual(before,after)
            finally:db.close()


if __name__=="__main__":
    unittest.main()
