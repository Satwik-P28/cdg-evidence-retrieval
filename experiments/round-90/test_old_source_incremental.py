"""R90 exact old-source FTS5 deletion and atomicity regressions."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from old_source_incremental import (
    create_legacy_contentless, update_with_prior_source,
    delete_with_prior_source, run, split_verified_source
)
from old_source_incremental import read, query, configure_mode, fts5_global_stats


DOCS = [
    {"doc_id": 11, "title": "alphacobalt", "abstract": ["Original blue phase."]},
    {"doc_id": 22, "title": "betacarbon", "abstract": ["Original green phase."]},
    {"doc_id": 33, "title": "gammahelium", "abstract": ["Original violet phase."]},
]


class LegacyContentlessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/"contentless.sqlite"
        self.db = create_legacy_contentless(self.path, DOCS)
        configure_mode(self.db, "WAL")

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_old_source_sha_and_split(self):
        self.assertEqual(split_verified_source(read(self.db, 1)["source_bytes"]),
                         ("alphacobalt", "Original blue phase."))
        self.assertEqual(fts5_global_stats(self.db)[0], 3)
        self.assertEqual(query(self.db, "alphacobalt"), [1])

    def test_one_correct_rename_preserves_stats_and_index(self):
        before = fts5_global_stats(self.db)
        self.assertEqual(update_with_prior_source(
            self.db, 1, "11", "deltalithium", ["Faster pink phase."]), 2)
        self.assertEqual(query(self.db, "alphacobalt"), [])
        self.assertEqual(query(self.db, "deltalithium"), [1])
        self.assertEqual(read(self.db, 1)["source_bytes"],
                         b"deltalithium\nFaster pink phase.")
        self.assertEqual(fts5_global_stats(self.db)[0], before[0])

    def test_many_updates_no_global_count_drift(self):
        for i in range(35):
            update_with_prior_source(self.db, 1, "11",
                                     "newterm"+str(i), ["Evidence "+str(i)])
            self.assertEqual(fts5_global_stats(self.db)[0], 3)
        self.assertEqual(query(self.db, "newterm34"), [1])
        self.assertEqual(query(self.db, "newterm0"), [])

    def test_every_injected_failure_preserves_original_source_and_fts(self):
        original = read(self.db, 1)
        stats = fts5_global_stats(self.db)
        for fault in ("after_delete", "after_insert", "after_payload"):
            with self.assertRaises(RuntimeError):
                update_with_prior_source(self.db, 1, "11", "wronggalaxy",
                                         ["Never persisted."], fault=fault)
            self.assertEqual(read(self.db, 1), original)
            self.assertEqual(query(self.db, "alphacobalt"), [1])
            self.assertEqual(query(self.db, "wronggalaxy"), [])
            self.assertEqual(fts5_global_stats(self.db), stats)

    def test_delete_and_rollback(self):
        with self.assertRaises(RuntimeError):
            delete_with_prior_source(self.db, 2, "22", "after_index")
        self.assertEqual(query(self.db, "betacarbon"), [2])
        delete_with_prior_source(self.db, 2, "22")
        self.assertEqual(query(self.db, "betacarbon"), [])
        with self.assertRaises(KeyError):
            read(self.db, 2)
        self.assertEqual(fts5_global_stats(self.db)[0], 2)

    def test_wrong_identity_or_corrupt_old_bytes_fail_closed(self):
        with self.assertRaises(KeyError):
            update_with_prior_source(self.db, 1, "999", "wrong",
                                     ["wrong"])
        with self.assertRaises(ValueError):
            update_with_prior_source(self.db, 1, "11", "has\nnewlines",
                                     ["invalid"])
        self.db.execute("UPDATE docs SET compressed=? WHERE rowid=1",
                        (b"damaged-zlib",))
        with self.assertRaises(ValueError):
            update_with_prior_source(self.db, 1, "11", "repair",
                                     ["no silent repair"])
        self.assertEqual(query(self.db, "alphacobalt"), [1])

    def test_unicode_byte_exact_update_and_original_receipt(self):
        update_with_prior_source(self.db, 1, "11", "Café研究",
                                 ["Résumé signal 🧪"])
        self.assertEqual(read(self.db, 1)["source_bytes"],
                         "Café研究\nRésumé signal 🧪".encode("utf8"))
        self.assertEqual(fts5_global_stats(self.db)[0], 3)

    def test_four_differential_comparisons(self):
        result = run(full_data=False)
        self.assertEqual(len(result["results"]), 4)
        for row in result["results"]:
            self.assertEqual(row["stats"]["full"], row["stats"]["r90"])
            self.assertEqual(row["top10_equal_to_full_control"]["r90"], 10)
            self.assertEqual(row["updated_docs_verified"],
                             row["distinct_modified"])
            self.assertGreater(row["storage_bytes"]["vacuumed"]["r90"], 0)


if __name__=="__main__":
    unittest.main()
