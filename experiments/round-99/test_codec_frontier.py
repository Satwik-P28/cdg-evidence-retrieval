"""R99 standard codec integrity, original-source and FTS invariant tests."""
import tempfile
import unittest
from pathlib import Path
import sqlite3

from codec_frontier import (
    CODECS,encode,decode,benchmark_corpus,read_codec,MAX_OUTPUT
)


DOCS=[
    {"doc_id":i+1,"title":"Sample mineral"+str(i),
     "abstract":["A record from an experiment with repeated bytes. "*4,
                 "Experiment "+str(i)+" has full original evidence."]}
    for i in range(12)
]


class SourceCodecTests(unittest.TestCase):
    def test_all_six_codecs_round_trip_exact_unicode(self):
        payload="Český evidence 🧬\nScientific result.".encode("utf8")
        for method in CODECS:
            blob=encode(method,payload)
            self.assertEqual(decode(method,blob,len(payload)),payload)

    def test_no_codec_may_silently_truncate_original(self):
        payload=b"Original evidence held constant."*30
        for method in CODECS:
            encoded=encode(method,payload)
            with self.assertRaises(ValueError):
                decode(method,encoded,len(payload)-1)

    def test_wrong_codec_is_rejected(self):
        with self.assertRaises(ValueError):
            encode("inventedcodec",b"data")
        with self.assertRaises(ValueError):
            decode("inventedcodec",b"data",4)

    def test_sanity_bound_prevents_claimed_gigantic_original(self):
        with self.assertRaises(ValueError):
            decode("zlib6",encode("zlib6",b"ok"),MAX_OUTPUT+1)

    def test_malformed_zlib_fails_closed(self):
        payload=b"some evidence"
        blob=encode("zlib6",payload)
        with self.assertRaises((ValueError,Exception)):
            decode("zlib6",blob[:-4],len(payload))
        with self.assertRaises((ValueError,Exception)):
            decode("zlib6",blob+b"extra",len(payload))

    def test_malformed_lzma_fails_closed(self):
        payload=b"some evidence"
        blob=encode("lzma6",payload)
        with self.assertRaises((ValueError,Exception)):
            decode("lzma6",blob[:-3],len(payload))

    def test_compressor_values_not_silently_relabeled(self):
        with tempfile.TemporaryDirectory() as root:
            from old_source_incremental import create_legacy_contentless
            path=Path(root)/"test.sqlite"
            db=create_legacy_contentless(path,DOCS)
            db.execute("ALTER TABLE docs ADD COLUMN codec TEXT NOT NULL DEFAULT 'zlib6'")
            try:
                original=read_codec(db,1,"1")
                self.assertIn(b"Sample mineral0",original)
                db.execute("UPDATE docs SET codec='brotli5' WHERE rowid=1")
                with self.assertRaises(Exception):
                    read_codec(db,1,"1")
            finally:
                db.close()

    def test_two_codec_source_archives_preserve_same_FTS_index(self):
        result=benchmark_corpus(
            "tiny",DOCS,[1,2,3,2,1],"fixture-sha",
            codecs=("zlib6","zstd3"))
        self.assertEqual(result["docs"],len(DOCS))
        self.assertEqual(len(result["codecs"]),2)
        self.assertTrue(all(row["sha_verified_original_source_docs"]==len(DOCS)
                            for row in result["codecs"]))
        self.assertTrue(all(row["retained_fts_global_stats_unchanged"]
                            for row in result["codecs"]))

    def test_codec_label_expected_in_schema_source_reader(self):
        with tempfile.TemporaryDirectory() as root:
            from old_source_incremental import create_legacy_contentless
            db=create_legacy_contentless(Path(root)/"test.sqlite",DOCS)
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    read_codec(db,1,"1")
            finally:
                db.close()


if __name__=="__main__":
    unittest.main()
