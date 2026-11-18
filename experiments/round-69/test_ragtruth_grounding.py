import copy
import hashlib
import unittest

from ragtruth_grounding import (
    REVISION,BLOBS,POLICIES,git_blob,source_text,
    sentence_flags,predictions,annotated_masks,select_sources,
    one_confusion,evaluate,ratios,
)


def source(sid,text):
    return {
        'source_id':sid,'task_type':'QA',
        'source_info':{'question':'Where is the inventor?','passages':text}
    }


def response(id,sid,content,labels=None,split='test',quality='good'):
    return {'id':id,'source_id':sid,'response':content,
            'labels':labels or [],'split':split,'quality':quality}


class GroundingTests(unittest.TestCase):
    def test_revision_pinned_and_distinct_sources(self):
        self.assertEqual(len(REVISION),40)
        self.assertEqual(set(BLOBS),{
            'dataset/response.jsonl','dataset/source_info.jsonl'})
        self.assertEqual(len(git_blob(b'Hello')),40)
        self.assertEqual(git_blob(b'Hello'),
                         hashlib.sha1(b'blob 5\0Hello').hexdigest())

    def test_literal_source_has_no_fabricated_label(self):
        s='The inventor lived in Berlin and worked in 1998.'
        self.assertEqual(sentence_flags(
            'The inventor lived in Berlin and worked in 1998.',s
        )['number_entity_guard'],False)
        self.assertTrue(sentence_flags(
            'The inventor lived in Paris in 2017.',s
        )['number_entity_guard'])
        result=predictions('The inventor worked in Berlin.',s)
        self.assertEqual(set(result),set(POLICIES))
        self.assertFalse(any(result['accept_all']))
        self.assertTrue(all(result['reject_all']))

    def test_span_labels_and_implicit_truth_separate(self):
        value='Berlin was founded by aliens.'
        start=value.index('aliens')
        labelled={'start':start,'end':start+6,'text':'aliens',
                  'label_type':'Subtle Baseless Info','implicit_true':True}
        gold,strict,issues=annotated_masks(response('r','s',value,[labelled]))
        self.assertTrue(any(gold))
        self.assertFalse(any(strict))
        self.assertFalse(issues)
        bad=copy.deepcopy(labelled)
        bad['text']='different'
        _,_,issues=annotated_masks(response('r','s',value,[bad]))
        self.assertEqual(issues,['text_mismatch'])

    def test_source_level_sampling_and_train_separation(self):
        sources={str(i):source(str(i),'Text.') for i in range(5)}
        records=[response('r-'+str(i),str(i),'Answer.')
                 for i in range(5)]
        records.append(response('train','0','secret','',split='train'))
        sample,meta=select_sources(records,sources,group_cap=3)
        self.assertEqual(meta['selected_source_groups'],3)
        self.assertTrue(all(x['split']=='test' for x in sample))
        self.assertNotIn('train',{x['id'] for x in sample})
        self.assertEqual(len(sample),3)

    def test_aggregate_human_labels_without_training_leak(self):
        sources=[source('a','The inventor lived in Berlin in 1998.'),
                 source('b','The artist lived in Rome in 2007.')]
        content='The inventor lived in Paris in 2017.'
        begin=content.index('Paris')
        records=[
            response('r1','a',content,[{'start':begin,'end':begin+5,
                        'text':'Paris','label_type':'Evident Conflict'}]),
            response('r2','a','The inventor lived in Berlin in 1998.'),
            response('r3','b','The artist lived in Rome in 2007.')
        ]
        output=evaluate(records,sources,group_cap=2)
        self.assertEqual(output['n'],3)
        self.assertEqual(output['question_group_count'],2)
        self.assertEqual(output['human_label_overview']['labelled_response'],1)
        self.assertEqual(output['methods']['accept_all']['response']['fn'],1)
        self.assertEqual(output['methods']['reject_all']['response']['tp'],1)
        self.assertEqual(output['methods']['reject_all']['response']['fp'],2)
        self.assertEqual(output['methods']['accept_all']['response']['tn'],2)
        for method in POLICIES:
            self.assertEqual(sum(output['methods'][method]['response'][x]
                                 for x in ('tp','tn','fp','fn')),3)
            self.assertEqual(sum(output['methods'][method]['char'][x]
                                 for x in ('tp','tn','fp','fn')),
                             sum(len(x['response']) for x in records))
        self.assertGreaterEqual(output['methods']['number_entity_guard']['response']['tp'],1)

    def test_binary_confusion_and_no_oracle(self):
        self.assertEqual(one_confusion([True,False,True],[True,True,False]),
                         (1,1,1,0))
        self.assertEqual(ratios(1,1,1)['f1'],.5)
        s=source('id','The number was 100.')
        a=response('x','id','The number was 200.')
        b=copy.deepcopy(a)
        b['labels']=[{'start':15,'end':18,'text':'200','label_type':'Conflict'}]
        a['labels']=[]
        # Predictions depend exclusively on retrieved source and response,
        # not on human annotations.
        self.assertEqual(
            predictions(a['response'],source_text(s)),
            predictions(b['response'],source_text(s)))


if __name__=='__main__':
    unittest.main()
