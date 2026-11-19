"""R100 per-source codec selection and original-source archive invariants."""
import unittest
from adaptive_codec import (
    CANDIDATES,POLICIES,policy_candidates,choose_codec,
    build_candidate_pool,benchmark_corpus
)


DOCS=[
    {"doc_id":i+1, "title":"Specimen"+str(i),
     "abstract":["Repeated scientific observation."*6,
                 "A unique interpretation "+str(i)+"."]}
    for i in range(13)
]


def example_lengths(a,b,c):
    return {"zlib6":b"a"*a,"zstd3":b"b"*b,"brotli5":b"c"*c}


class AdaptiveCodecTests(unittest.TestCase):
    def test_same_source_codec_minimum_chooses_lowest_blob(self):
        self.assertEqual(choose_codec(
            "per_source_smallest_of_three",example_lengths(120,100,110)),
            "zstd3")
        self.assertEqual(choose_codec(
            "per_source_smallest_of_three",example_lengths(100,120,90)),
            "brotli5")

    def test_fixed_threshold_prefers_fast_zstd_when_brotli_gain_small(self):
        self.assertEqual(choose_codec(
            "zstd3_unless_brotli_saves_64",example_lengths(110,100,60)),
            "zstd3")
        self.assertEqual(choose_codec(
            "zstd3_unless_brotli_saves_64",example_lengths(110,130,60)),
            "brotli5")

    def test_higher_threshold_delays_brotli(self):
        x=example_lengths(300,200,110)
        self.assertEqual(choose_codec(
            "zstd3_unless_brotli_saves_64",x),"brotli5")
        self.assertEqual(choose_codec(
            "zstd3_unless_brotli_saves_128",x),"zstd3")

    def test_threshold_can_reference_zlib_source_codec(self):
        self.assertEqual(choose_codec(
            "zlib6_unless_brotli_saves_64",example_lengths(140,30,50)),
            "brotli5")
        self.assertEqual(choose_codec(
            "zlib6_unless_brotli_saves_64",example_lengths(60,30,50)),
            "zlib6")

    def test_candidate_encoding_requirements_are_explicit(self):
        self.assertEqual(policy_candidates("all_brotli5"),("brotli5",))
        self.assertEqual(policy_candidates("per_source_smallest_of_three"),
                         CANDIDATES)
        self.assertEqual(policy_candidates("zstd3_unless_brotli_saves_64"),
                         ("zstd3","brotli5"))

    def test_invalid_policy_is_not_silently_fallback(self):
        with self.assertRaises(ValueError):
            policy_candidates("unknown")
        with self.assertRaises(ValueError):
            choose_codec("unknown",{})

    def test_candidate_compression_pool_preserves_original_byte_diversity(self):
        data=[b"a"*300,b"\x01"*50,b"hello science"]
        pool,timing=build_candidate_pool(data)
        self.assertEqual(set(pool),set(CANDIDATES))
        self.assertEqual(set(timing),set(CANDIDATES))
        self.assertTrue(all(len(pool[codec])==len(data) for codec in CANDIDATES))
        self.assertTrue(all(timing[codec]>=0 for codec in CANDIDATES))

    def test_mixed_policy_keeps_same_FTS_index_and_SHA_verified_source(self):
        result=benchmark_corpus(
            "fixture",DOCS,[1,2,1,7,3],"fixture",
            policies=("all_brotli5","per_source_smallest_of_three",
                      "zstd3_unless_brotli_saves_64"))
        self.assertEqual(result["docs"],len(DOCS))
        self.assertEqual(len(result["policies"]),3)
        for row in result["policies"]:
            self.assertEqual(row["original_sources_sha_verified"],len(DOCS))
            self.assertEqual(sum(row["source_codec_histogram"].values()),len(DOCS))
            self.assertTrue(row["index_stats_unchanged"])
            self.assertEqual(row["warm_reads_with_sha"]["count"],15)

    def test_codec_minimum_never_selects_nonpredeclared_algorithm(self):
        examples=[
            example_lengths(50,60,70),
            example_lengths(100,100,100),
            example_lengths(120,90,95)
        ]
        for row in examples:
            self.assertIn(choose_codec("per_source_smallest_of_three",row),
                          CANDIDATES)


if __name__=="__main__":
    unittest.main()
