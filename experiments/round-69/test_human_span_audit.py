import hashlib
import json
import unittest
from human_span_audit import (
    FILES,REVISION,git_blob_sha,validate_labels,span_kind,sentence_ranges,
    proxy_score,fetch_pinned,audit,metrics_from_confusion,wilson_95
)


class HumanLabelsTests(unittest.TestCase):
    def test_pinned_blobs_fail_closed(self):
        self.assertEqual(len(REVISION),40)
        self.assertEqual(len(FILES),2)
        for path,blobsha in FILES.values():
            self.assertEqual(len(blobsha),40)
            self.assertTrue(path.startswith('dataset/'))
        self.assertEqual(git_blob_sha(b'a'),
                         hashlib.sha1(b'blob 1\0a').hexdigest())
        with self.assertRaises(ValueError):
            fetch_pinned('responses',download_fn=lambda url:b'not upstream data')

    def test_span_integrity_and_semantic_label_groups(self):
        response='The launch took place in Paris, not London.'
        labels=[
            {'start':25,'end':30,'text':'Paris','label_type':'Evident Baseless Info'},
            {'start':36,'end':42,'text':'London','label_type':'Evident Conflict'},
            {'start':0,'end':3,'text':'bad','label_type':'Evident Conflict'},
        ]
        good,bad=validate_labels(response,labels)
        self.assertEqual(bad,1)
        self.assertEqual(len(good),2)
        self.assertEqual(span_kind(good[0][2]),'baseless')
        self.assertEqual(span_kind(good[1][2]),'contradictory')
        self.assertEqual(span_kind({'label_type':'Evident Conflict','implicit_true':True}),
                         'implicit_true')

    def test_negative_lexical_controls_and_tokens(self):
        source='The movie was directed by Jane Doe in France.'
        self.assertGreater(proxy_score('Directed by Jane Doe',source),.5)
        self.assertEqual(proxy_score('The telescope vanished in Nigeria.',source),0)
        self.assertEqual(proxy_score('',source),0)
        self.assertEqual(len(sentence_ranges('One thing. Another thing!')),2)

    def test_wilson_zero_matches_has_nonzero_upper_bound(self):
        lo,hi=wilson_95(0,235)
        self.assertEqual(lo,0)
        self.assertGreater(hi,0)
        self.assertLess(hi,.03)
        self.assertIsNone(wilson_95(0,0))

    def test_confusion_boundary(self):
        out=metrics_from_confusion({'tp':4,'fp':2,'tn':8,'fn':1})
        self.assertAlmostEqual(out['precision'],4/6,places=4)
        self.assertAlmostEqual(out['recall'],4/5,places=4)
        self.assertEqual(out['support_citation_false_accepts'],1)

    def test_end_to_end_human_annotation_receipts_fixture(self):
        source_info=[{
            'source_id':'s1','task_type':'QA',
            'source_info':{'question':'Where was the event?',
                           'passages':'Paris hosted the ceremony, while London was mentioned.'}
        },{
            'source_id':'s2','task_type':'QA',
            'source_info':{'question':'Where was the conference?',
                           'passages':'The meeting occurred in Canada.'}
        }]
        responses=[
            {'id':'1','source_id':'s1','split':'test','quality':'good','model':'fixture',
             'response':'The ceremony occurred in London.','labels':[
                 {'start':25,'end':31,'text':'London',
                  'label_type':'Evident Conflict'}]},
            {'id':'2','source_id':'s2','split':'test','quality':'good','model':'fixture',
             'response':'The meeting occurred in Canada.','labels':[]},
            {'id':'3','source_id':'s1','split':'train','quality':'good','model':'fixture',
             'response':'The ceremony occurred in Paris.','labels':[]},
        ]
        out=audit(source_info,responses)
        self.assertEqual(out['good_test_qa_responses'],2)
        self.assertEqual(out['source_id_count'],2)
        self.assertEqual(out['human_annotation_spans'],1)
        self.assertEqual(out['span_categories']['contradictory']['literal_source_citations'],1)
        self.assertEqual(out['strict_source_receipts_issued_for_annotated_spans'],1)
        self.assertEqual(out['train_test_same_source_id_count_all_tasks'],1)
        self.assertGreater(out['whole_archive_bytes'],0)
        self.assertGreater(out['gear512_archive_bytes'],0)
        self.assertGreaterEqual(out['sentence_chunks'],2)

    def test_bad_offsets_reported_not_converted_to_false_truth(self):
        src=[{'source_id':'x','task_type':'QA',
              'source_info':{'question':'Q','passages':'The sky is blue.'}}]
        response=[{'id':'1','source_id':'x','split':'test','quality':'good',
                   'response':'The sky is green.','labels':[
                       {'start':0,'end':4,'text':'WRONG','label_type':'Conflict'}]}]
        out=audit(src,response)
        self.assertEqual(out['invalid_annotation_spans'],1)
        self.assertEqual(out['human_annotation_spans'],0)
        self.assertGreaterEqual(out['sentence_chunks'],1)


if __name__=='__main__':unittest.main()
