import unittest
from prompt_framing import (
    predicted_mask,predict_prompt,metrics_for_rows,group_bootstrap,
    R76,SALT,
)


class FakeModel:
    def predict_prompt(self,prompt,answer,output_format='spans',min_confidence=0.0):
        start=answer.find('Paris')
        if start<0:return []
        return [{'start':start,'end':start+5,'text':'Paris','confidence':.9}]


class PromptFramingTests(unittest.TestCase):
    def test_fixed_sample_contract(self):
        self.assertTrue(SALT.startswith('CDG-R77'))
        self.assertEqual(R76.name,'byte_exact_windows.py' if False else 'lettuce_reference.py')

    def test_prompt_span_response_offsets(self):
        answer='She lived in Paris.'
        mask,wall=predict_prompt(FakeModel(),'Original source provided.',answer)
        self.assertEqual(sum(mask),5)
        self.assertGreaterEqual(wall,0)
        self.assertEqual(predicted_mask(answer,[{
            'start':13,'end':18,'text':'Paris'}]),mask)

    def test_wrong_response_offset_rejected(self):
        with self.assertRaises(ValueError):
            predicted_mask('Test',[{'start':5,'end':9,'text':'fail'}])
        with self.assertRaises(ValueError):
            predicted_mask('Test',[{'start':0,'end':4,'text':'Other'}])

    def test_paired_response_scoring_and_group_bootstrap(self):
        rows=[]
        for i in range(4):
            for k in range(3):
                gold=k==0
                rows.append({
                    'sid':str(i),
                    'human_positive':gold,
                    'context':{'flag':True},
                    'original_prompt':{'flag':gold}
                })
        a=metrics_for_rows(rows,'context')
        b=metrics_for_rows(rows,'original_prompt')
        self.assertEqual(a['tp'],4)
        self.assertEqual(a['fp'],8)
        self.assertEqual(b['tp'],4)
        self.assertEqual(b['fp'],0)
        self.assertEqual(b['f1'],1)
        ci=group_bootstrap(rows,reps=100)
        self.assertEqual(ci,group_bootstrap(rows,reps=100))
        self.assertGreater(ci[0],0)


if __name__=='__main__':unittest.main()
