"""R88 regressions for caller-level snapshot isolation and real SIGKILL exits."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from snapshot_kill_probe import (
    FIXTURE, NEW_TITLE, NEW_ABSTRACT, NEW_BYTES, OLD_BYTES,
    configure_mode, concurrency_probe, crash_matrix, retrieve_snapshot,
)
from snapshot_kill_probe import create_db, atomic_update, query, read


class SnapshotAndCrashTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/"source.sqlite"
        self.conn, _ = create_db(self.path, FIXTURE)
        configure_mode(self.conn, "WAL")

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def test_unsafe_query_then_read_can_fracture_under_committed_update(self):
        reader = sqlite3.connect(str(self.path), isolation_level=None)
        try:
            result = query(reader, "oldquartz")
            self.assertEqual(result, [1])
            atomic_update(self.conn, 1, "101", NEW_TITLE, NEW_ABSTRACT)
            current = read(reader, result[0])
            self.assertEqual(current["source_bytes"], NEW_BYTES)
            self.assertEqual(query(reader, "oldquartz"), [])
            self.assertEqual(query(reader, "newnebula"), [1])
        finally:
            reader.close()

    def test_single_read_snapshot_keeps_same_evidence_generation(self):
        reader = sqlite3.connect(str(self.path), isolation_level=None)
        try:
            def writer_commit():
                atomic_update(self.conn, 1, "101", NEW_TITLE, NEW_ABSTRACT)
            ranked = retrieve_snapshot(reader, "oldquartz", interleave=writer_commit)
            self.assertEqual([r for r, _ in ranked], [1])
            self.assertEqual(ranked[0][1]["source_bytes"], OLD_BYTES)
            self.assertEqual(ranked[0][1]["generation"], 1)
            self.assertEqual(read(reader, 1)["source_bytes"], NEW_BYTES)
            self.assertEqual(query(reader, "newnebula"), [1])
        finally:
            reader.close()

    def test_snapshot_failure_rolls_back_read_transaction(self):
        reader = sqlite3.connect(str(self.path), isolation_level=None)
        try:
            def fail():
                raise RuntimeError("interleaving fault")
            with self.assertRaisesRegex(RuntimeError, "interleaving fault"):
                retrieve_snapshot(reader, "oldquartz", interleave=fail)
            self.assertFalse(reader.in_transaction)
            atomic_update(self.conn, 1, "101", NEW_TITLE, NEW_ABSTRACT)
            self.assertEqual(query(reader, "newnebula"), [1])
        finally:
            reader.close()

    def test_snapshot_rejects_nested_transaction(self):
        self.conn.execute("BEGIN")
        try:
            with self.assertRaisesRegex(RuntimeError, "existing transaction"):
                retrieve_snapshot(self.conn, "oldquartz")
        finally:
            self.conn.execute("ROLLBACK")

    def test_process_sigkill_between_payload_index_and_commit(self):
        # Fresh independent database for each mode x crash boundary.
        cases = crash_matrix()
        self.assertEqual(len(cases), 6)
        for mode in ("DELETE", "WAL"):
            for stage in ("after_payload", "after_index", "after_commit"):
                case = next(c for c in cases
                            if c["journal_mode"] == mode and c["kill_stage"] == stage)
                self.assertEqual(case["child_exit"], "SIGKILL")
                self.assertEqual(case["fts5_integrity"], "pass")
                self.assertTrue(case["source_sha256_checked"])
                self.assertEqual(case["generation"], 2 if stage == "after_commit" else 1)

    def test_integrated_race_reproduction(self):
        result = concurrency_probe()
        self.assertTrue(result["legacy_split_search_then_read_fractured"])
        self.assertTrue(result["snapshot_old_bytes_preserved"])
        self.assertTrue(result["source_changes_visible_after_snapshot"])


if __name__ == "__main__":
    unittest.main()
