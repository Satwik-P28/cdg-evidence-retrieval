import unittest
from lettuce_reference import (
    MODEL_ID,MODEL_REVISION,MODEL_LICENSE,MAX_TOKENS,
    assemble_context,audited_prediction,confusion,micro,evaluate,load,R69,
)


def source(sid,task):
    if task=='QA':
        info={'question':'Where was the city?',
              'passages':'passage 1: Berlin is in Germany.\n\npassage 2: Paris is in France.'}
    else:
        info=' '.join(['This story describes Berlin and Germany.']*200)
    return {'source_id':sid,'task_type':task,'source_info':info}


def response(sid,text,positive=False):
    labels=[]
    if positive:
        left=text.index('Paris')
        labels=[{'start':left,'end':left+5,'text':'Paris',
                 'label_type':'Evident Conflict'}]
    return {'id':'id-'+sid,'source_id':sid,'response':text,'labels':labels,
            'split':'test','quality':'good'}


class FakeDetector:
    class Driver:
        class Tokenizer:
            def encode(self,text,add_special_tokens=True):
                return list(range(len(text.split())+int(add_special_tokens)))
        tokenizer=Tokenizer()
    detector=Driver()
    def predict(self,context,answer,question=None,output_format='spans',
                min_confidence=0.0):
        if 'Paris' not in answer:return []
        left=answer.index('Paris')
        return [{'start':left,'end':left+5,'text':'Paris',
                 'confidence':.8}]


class DetectorBaselineTests(unittest.TestCase):
    def setUp(self):
        self.r69=load('r69_for76_test',R69)

    def test_model_pin_is_immutable_and_policy_fixed(self):
        self.assertEqual(len(MODEL_REVISION),40)
        self.assertIn('lettucedect-base',MODEL_ID)
        self.assertEqual(MODEL_LICENSE,'MIT')
        self.assertEqual(MAX_TOKENS,2048)

    def test_qa_context_preserves_multiple_passages(self):
        context,question,meta=assemble_context(source('qa','QA'),self.r69)
        self.assertEqual(len(context),2)
        self.assertEqual(question,'Where was the city?')
        self.assertFalse(meta['source_limited'])
        self.assertIn('Berlin',context[0])
        self.assertIn('Paris',context[1])

    def test_summary_context_bounded_without_fabricated_claims(self):
        context,question,meta=assemble_context(source('summary','Summary'),self.r69)
        self.assertIsNone(question)
        self.assertGreater(len(context),1)
        self.assertLessEqual(max(len(s.split()) for s in context),150)
        self.assertEqual(meta['source_words_used'] if 'source_words_used' in meta
                         else meta['source_used_words'],meta['source_total_words'])

    def test_predicted_hallucination_offsets_are_audited(self):
        answer='The artist lived in Paris.'
        mask,info=audited_prediction(
            FakeDetector(),['Berlin is in Germany.'],answer,None)
        self.assertEqual(sum(mask),5)
        self.assertEqual(info['spans'],1)
        self.assertEqual(answer[answer.index('Paris'):
                                answer.index('Paris')+5],'Paris')

    def test_error_on_invalid_span(self):
        class Invalid(FakeDetector):
            def predict(self,*args,**kwargs):
                return [{'start':0,'end':99,'text':'missing',
                         'confidence':.99}]
        with self.assertRaises(ValueError):
            audited_prediction(Invalid(),['Source'],'Short answer',None)

    def test_confusion_and_model_free_full_evaluation(self):
        gold=[False,True,True,False]
        pred=[False,True,False,True]
        self.assertEqual(confusion(pred,gold),{
            'tp':1,'fp':1,'fn':1,'tn':1})
        records=[
            response('qa','The artist lived in Paris.',True),
            response('sum','A record describes Berlin.',False)
        ]
        sources={'qa':source('qa','QA'),'sum':source('sum','Summary')}
        outcomes=evaluate(records,sources,FakeDetector(),self.r69)
        self.assertEqual(outcomes['all']['n'],2)
        self.assertEqual(outcomes['QA']['human_positive_responses'],1)
        self.assertEqual(outcomes['Summary']['human_positive_responses'],0)
        self.assertEqual(outcomes['all']['response_level']['tp'],1)
        self.assertEqual(outcomes['all']['response_level']['tn'],1)
        self.assertEqual(outcomes['all']['character_level']['tp'],5)


if __name__=='__main__':unittest.main()
