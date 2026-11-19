"""R96 QASPER release provenance and evidence-map parsing regressions."""
import hashlib
import io
import json
import tarfile
import unittest

from qasper_source_probe import (
    EXPECTED_SHA,normalize,article_paragraphs,questions,
    answer_evidences,source_probe,extract_official
)


def fixture():
    return {
        "title":"Controlled system",
        "full_text":{
            "section_name":["Introduction","Methods"],
            "paragraphs":[
                ["A model was measured on original samples.","A detailed other source."],
                ["Inference was calibrated using training alone."]]
        },
        "qas":[
            {"question":"What was measured?","question_id":"q1","answers":[
                {"answer":{"evidence":[
                    "A model was measured on original samples.",
                    "FLOAT SELECTED fig1"]}},
                {"answer":{"evidence":["Not an original paragraph."]}},
            ]},
            {"question":"How calibrated?","question_id":"q2","answers":[
                {"answer":{"evidence":[
                    "Inference was calibrated using training alone."]}}
            ]}
        ],
    }


class QasperPreflightTests(unittest.TestCase):
    def test_source_normalization_whitespace_only(self):
        self.assertEqual(normalize(" one \n two\t"),"one two")
        self.assertEqual(normalize(None),"")

    def test_paragraphs_preserve_section_positions(self):
        rows=article_paragraphs(fixture())
        self.assertEqual(len(rows),3)
        self.assertEqual(rows[2]["section"],1)
        self.assertEqual(rows[2]["paragraph"],0)

    def test_array_qas_schema_matches_list_schema(self):
        raw=fixture()
        arr={"qas":{
            "question":[x["question"] for x in raw["qas"]],
            "question_id":[x["question_id"] for x in raw["qas"]],
            "answers":[x["answers"] for x in raw["qas"]]}}
        self.assertEqual(list(questions(raw)),list(questions(arr)))

    def test_normalized_nested_answer_examples(self):
        a={"answer":{"evidence":["Evidence paragraph."]}}
        self.assertEqual(list(answer_evidences(a)),[["Evidence paragraph."]])
        b={"answer":[{"evidence":["A."]},{"evidence":["B."]}]}
        self.assertEqual(list(answer_evidences(b)),[["A."],["B."]])

    def test_exact_gold_evidence_not_wrong_source_transfer(self):
        stats=source_probe({"paper-1":fixture()})
        c=stats["counts"]
        self.assertEqual(c["articles"],1)
        self.assertEqual(c["questions"],2)
        self.assertEqual(c["annotation_instances"],3)
        self.assertEqual(c["evidence_strings_exact_paragraph_matched"],2)
        self.assertEqual(c["evidence_strings_unmatched"],1)
        self.assertEqual(c["table_figure_evidence"],1)
        self.assertEqual(c["annotations_with_at_least_one_exact_paragraph"],2)

    def test_duplicate_question_in_paper_rejected(self):
        a=fixture()
        a["qas"].append(a["qas"][0])
        with self.assertRaises(AssertionError):
            source_probe({"paper-1":a})

    def test_missing_sections_fail_closed(self):
        a=fixture()
        a["full_text"]["section_name"].pop()
        with self.assertRaises(AssertionError):
            article_paragraphs(a)

    def test_wrong_qas_schema_rejected(self):
        with self.assertRaises(AssertionError):
            list(questions({"qas":{"question":["yes"]}}))

    def test_non_official_tar_sha_rejected(self):
        archive=io.BytesIO()
        with tarfile.open(fileobj=archive,mode="w:gz") as tar:
            blob=json.dumps({"paper-1":fixture()}).encode()
            for name in ("qasper-train.json","qasper-dev.json"):
                info=tarfile.TarInfo(name=name)
                info.size=len(blob)
                tar.addfile(info,io.BytesIO(blob))
        self.assertNotEqual(hashlib.sha256(archive.getvalue()).hexdigest(),EXPECTED_SHA)
        with self.assertRaises(AssertionError):
            extract_official(archive.getvalue())


if __name__=="__main__":
    unittest.main()
