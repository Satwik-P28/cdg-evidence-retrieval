"""R89 model-free differential checks. Full 5,183-doc version runs in CI."""
import unittest
from dynamic_workloads import benchmark, revision_events, run


DOCS = [
    {"doc_id": i+1, "title": "crystal"+str(i),
     "abstract": ["Original observation "+str(i)+"."]}
    for i in range(15)
]
CLAIMS = [{"id": i, "claim": "crystal"+str(i)} for i in range(5)]


class DynamicWorkloadTests(unittest.TestCase):
    def test_diffuse_updates_unique_sources(self):
        events = revision_events(DOCS, "diffuse", 10)
        self.assertEqual(len({rid for rid, _, _, _ in events}), 10)
        self.assertEqual(len(events), 10)

    def test_hot_updates_reuse_same_sources(self):
        events = revision_events(DOCS, "hot", 30, hotset=3)
        self.assertEqual(len(events), 30)
        self.assertEqual(len({rid for rid, _, _, _ in events}), 3)

    def test_events_are_deterministic_and_invalid_settings_fail(self):
        self.assertEqual(revision_events(DOCS, "hot", 20, 4),
                         revision_events(DOCS, "hot", 20, 4))
        with self.assertRaises(ValueError):
            revision_events(DOCS, "diffuse", 16)
        with self.assertRaises(ValueError):
            revision_events(DOCS, "invalid", 4)

    def test_delete_mode_source_and_bm25_parity_under_revisions(self):
        events = revision_events(DOCS, "hot", 20, hotset=3)
        result = benchmark(DOCS, CLAIMS, events, "DELETE", "hot")
        self.assertEqual(result["verification"]["identical_top10_rankings"], 5)
        self.assertEqual(result["verification"]["atomic_fts5_stat_doc_count_and_column_tokens"][0], 15)
        self.assertGreater(result["verification_before_rebuild"]["atomic_fts5_stat_doc_count_and_column_tokens"][0], 15)
        self.assertEqual(result["verification"]["revised_source_bytes_verified"], 3)
        for state in ("initial", "active_after_updates", "after_checkpoint",
                      "after_vacuum_and_checkpoint"):
            self.assertGreater(result["storage_bytes"][state]["full"], 0)
            self.assertGreater(result["storage_bytes"][state]["atomic"], 0)

    def test_wal_mode_source_and_bm25_parity_under_revisions(self):
        events = revision_events(DOCS, "diffuse", 12)
        result = benchmark(DOCS, CLAIMS, events, "WAL", "diffuse")
        self.assertEqual(result["verification"]["revised_source_bytes_verified"], 12)
        self.assertEqual(result["verification"]["identical_top10_rankings"], 5)
        self.assertEqual(result["latency"]["atomic"]["events"], 12)
        self.assertEqual(result["latency"]["full"]["events"], 12)

    def test_four_independent_synthetic_architecture_comparisons(self):
        result = run(full_data=False)
        self.assertEqual(len(result["experiments"]), 4)
        self.assertEqual({x["revision_pattern"] for x in result["experiments"]},
                         {"hot", "diffuse"})
        self.assertEqual({x["journal_mode"] for x in result["experiments"]},
                         {"DELETE", "WAL"})


if __name__ == "__main__":
    unittest.main()
