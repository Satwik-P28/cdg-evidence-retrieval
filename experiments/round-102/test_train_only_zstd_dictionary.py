"""R102 original independent train-data dictionary integrity and controls."""
import tempfile
import unittest
from pathlib import Path

from train_only_zstd_dictionary import (
    DICT_SIZES,parse_variant,independently_trained_samples,
    train_dictionaries,base_archive,make_variant,OriginalSourceReader,
    evaluate
)
from qasper_paragraph_retrieval import load_dev


def paper(pid,count,with_questions=True):
    text=[
        "Scientific method for experimental evidence and results. "
        + "Measurements in " + str(i) + " were obtained for "
        + pid + " with robust testing of the original calculation. "*3
        for i in range(count)]
    return {
        "full_text":{"section_name":["Methods"],
                     "paragraphs":[text]},
        "qas":[{
            "question":"Which scientific method?", "question_id":pid+"-question",
            "answers":[{"answer":{"evidence":[text[0]]}}],
        }] if with_questions else [],
    }


TRAIN={
    "train-"+str(i):paper("train-"+str(i),30,False)
    for i in range(10)
}
DEV={
    "dev-one":paper("dev-one",5),
    "dev-two":paper("dev-two",4),
}


class QasperDictionaryTests(unittest.TestCase):
    def test_original_source_sampling_is_deterministic_and_article_only(self):
        a,meta=independently_trained_samples(TRAIN,50)
        b,meta2=independently_trained_samples(TRAIN,50)
        self.assertEqual(a,b)
        self.assertEqual(meta,meta2)
        self.assertEqual(len(a),50)
        self.assertFalse(meta["qa_labels_seen"])
        self.assertFalse(meta["dev_paper_text_seen"])

    def test_training_source_ignores_mutated_human_annotations(self):
        changed={key:{**v,"qas":[{
            "question":"wrong original claim",
            "question_id":"modified",
            "answers":[{"answer":{"evidence":["unrelated"]}}]
        }]} for key,v in TRAIN.items()}
        a,meta=independently_trained_samples(TRAIN,70)
        b,meta2=independently_trained_samples(changed,70)
        self.assertEqual(a,b)
        self.assertEqual(meta["selected_docid_sha256"],
                         meta2["selected_docid_sha256"])

    def test_exact_zstd_shared_dictionary_roundtrip(self):
        import zstandard as zstd
        samples,_=independently_trained_samples(TRAIN,240)
        dictionaries=train_dictionaries(samples,(8192,))
        blob=dictionaries[8192]["raw"]
        self.assertGreater(len(blob),1000)
        zd=zstd.ZstdCompressionDict(blob)
        compressor=zstd.ZstdCompressor(level=3,dict_data=zd)
        decompressor=zstd.ZstdDecompressor(dict_data=zd)
        raw=samples[0]
        self.assertEqual(decompressor.decompress(
            compressor.compress(raw),max_output_size=len(raw)+1),raw)

    def test_codec_variant_names_are_fixed_and_fail_closed(self):
        self.assertEqual(parse_variant("brotli5"),("brotli5",None,None))
        self.assertEqual(parse_variant("zstd3"),("zstd",3,None))
        self.assertEqual(parse_variant("zstd9_dict16384"),("zstd",9,16384))
        with self.assertRaises(ValueError):
            parse_variant("zstd5_dict16384")
        with self.assertRaises(ValueError):
            parse_variant("zstd3_dict999")

    def test_dictionary_archive_preserves_original_dev_source(self):
        docs,_,_=load_dev(DEV)
        samples,_=independently_trained_samples(TRAIN,240)
        dictionaries=train_dictionaries(samples,(8192,))
        with tempfile.TemporaryDirectory() as scratch:
            p=Path(scratch)
            base=p/"base.sqlite"
            c=base_archive(base,docs)
            c.close()
            comp,meta=make_variant(
                p/"dict.sqlite",base,docs,"zstd3_dict8192",dictionaries)
            try:
                reader=OriginalSourceReader(comp)
                self.assertEqual(reader.dictionary_id,1)
                for i,row in enumerate(docs,1):
                    expected=(row["title"]+"\n"+" ".join(row["abstract"])).encode()
                    self.assertEqual(reader.read(i,str(row["doc_id"])),expected)
                self.assertEqual(comp.execute(
                    "SELECT COUNT(*) FROM source_dictionaries").fetchone()[0],1)
                # Zstd's trainer can return a smaller dictionary than the
                # requested capacity on small/repetitive fixtures. Charge
                # actual bytes and verify the persisted exact dictionary.
                self.assertEqual(
                    meta["dictionary_stored_bytes"],
                    len(dictionaries[8192]["raw"]))
                self.assertGreater(meta["dictionary_stored_bytes"],1000)
            finally:comp.close()

    def test_corrupt_dictionary_fails_before_source_read(self):
        docs,_,_=load_dev(DEV)
        samples,_=independently_trained_samples(TRAIN,240)
        dictionaries=train_dictionaries(samples,(8192,))
        with tempfile.TemporaryDirectory() as scratch:
            p=Path(scratch)
            db=base_archive(p/"base.sqlite",docs);db.close()
            comp,_=make_variant(p/"dict.sqlite",p/"base.sqlite",docs,
                                "zstd3_dict8192",dictionaries)
            try:
                comp.execute(
                    "UPDATE source_dictionaries SET payload=? WHERE dict_id=1",
                    (b"wrong!",))
                with self.assertRaises(ValueError):
                    OriginalSourceReader(comp)
            finally:comp.close()

    def test_wrong_document_dictionary_id_rejected(self):
        docs,_,_=load_dev(DEV)
        samples,_=independently_trained_samples(TRAIN,240)
        dictionaries=train_dictionaries(samples,(8192,))
        with tempfile.TemporaryDirectory() as scratch:
            p=Path(scratch)
            db=base_archive(p/"base.sqlite",docs);db.close()
            comp,_=make_variant(p/"dict.sqlite",p/"base.sqlite",docs,
                                "zstd3_dict8192",dictionaries)
            try:
                comp.execute("UPDATE docs SET dict_id=0 WHERE rowid=1")
                reader=OriginalSourceReader(comp)
                with self.assertRaises(ValueError):
                    reader.read(1)
            finally:comp.close()

    def test_wrong_original_source_sha_fails_closed(self):
        docs,_,_=load_dev(DEV)
        with tempfile.TemporaryDirectory() as scratch:
            p=Path(scratch)
            db=base_archive(p/"base.sqlite",docs);db.close()
            comp,_=make_variant(p/"brotli.sqlite",p/"base.sqlite",docs,
                                "brotli5",{})
            try:
                comp.execute(
                    "UPDATE docs SET sha256=? WHERE rowid=1",
                    (b"\xff"*32,))
                with self.assertRaises(ValueError):
                    OriginalSourceReader(comp).read(1)
            finally:comp.close()

    def test_disjoint_paper_guard_blocks_fit_to_development_leak(self):
        with self.assertRaises(AssertionError):
            evaluate(TRAIN,{"train-0":TRAIN["train-0"]},
                     variants=("brotli5",),dictionary_sizes=(8192,))

    def test_same_fts_rankings_across_brotli_and_train_dictionary(self):
        r=evaluate(TRAIN,DEV,variants=(
            "brotli5","zstd3","zstd3_dict8192"),dictionary_sizes=(8192,))
        self.assertEqual(len(r["archives"]),3)
        self.assertTrue(all(x["identical_question_rankings"]==2
                            for x in r["archives"]))
        self.assertEqual([x["original_source_docs_sha_verified"]
                          for x in r["archives"]],[9,9,9])


if __name__=="__main__":
    unittest.main()
