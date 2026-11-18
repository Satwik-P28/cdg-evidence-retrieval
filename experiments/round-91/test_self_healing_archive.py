"""R91 independent compressed-source replay and OS process kill regressions."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from self_healing_archive import (
    DOCS, create_legacy_contentless, read, query, fts5_global_stats,
    rebuild_from_compressed_docs, poison_index_without_touching_sources,
    kill_matrix, reader_snapshot_race, synthetic_repair
)


class ArchiveRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/"docs.sqlite"
        self.db=create_legacy_contentless(self.path,DOCS)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_rebuild_without_original_corpus(self):
        previous=fts5_global_stats(self.db)
        result=rebuild_from_compressed_docs(self.db)
        self.assertEqual(result["docs_rebuilt"],2)
        self.assertEqual(fts5_global_stats(self.db),previous)
        self.assertEqual(query(self.db,"oldzircon"),[1])

    def test_internal_fts_valid_but_source_provenance_wrong(self):
        poison_index_without_touching_sources(self.db)
        self.db.execute("INSERT INTO sources(sources) VALUES('integrity-check')")
        self.assertEqual(query(self.db,"spurioussearchtoken"),[1])
        self.assertEqual(read(self.db,1)["source_bytes"],
                         b"oldzircon\nOriginal light source.")

    def test_replay_fixes_independent_source_index_mismatch(self):
        poison_index_without_touching_sources(self.db)
        rebuild_from_compressed_docs(self.db)
        self.assertEqual(query(self.db,"spurioussearchtoken"),[])
        self.assertEqual(query(self.db,"oldzircon"),[1])

    def test_partial_rebuild_exceptions_rollback(self):
        poison_index_without_touching_sources(self.db)
        for stage in ("after_delete_all","after_first_insert"):
            with self.assertRaises(RuntimeError):
                rebuild_from_compressed_docs(self.db,stage)
            self.assertEqual(query(self.db,"spurioussearchtoken"),[1])

    def test_bad_compressed_blob_fail_closed_during_rebuild(self):
        self.db.execute("UPDATE docs SET compressed=? WHERE rowid=1",
                        (b"corrupt-stream",))
        with self.assertRaises(ValueError):
            rebuild_from_compressed_docs(self.db)
        self.assertEqual(query(self.db,"oldzircon"),[1])

    def test_eight_real_process_kills(self):
        cases=kill_matrix()
        self.assertEqual(len(cases),8)
        for case in cases:
            self.assertTrue(case["fts_and_source_recovered"])
            self.assertEqual(case["generation"],
                             2 if case["stage"]=="after_commit" else 1)
            self.assertEqual(case["fts_global_doc_count"],2)

    def test_reader_writer_snapshot(self):
        self.assertTrue(reader_snapshot_race()["old_generation_inside_read_snapshot"])

    def test_full_synthetic_self_repair(self):
        result=synthetic_repair()
        self.assertTrue(result["source_text_authenticated"])
        self.assertEqual(result["rebuild_rollback_injections"],2)
        self.assertEqual(result["repair"]["docs_rebuilt"],2)


if __name__=="__main__":
    unittest.main()
