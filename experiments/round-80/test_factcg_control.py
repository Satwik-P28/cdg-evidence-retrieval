import unittest
from factcg_control import prompt,INSTRUCTION,FACTCG_ID,FACTCG_SHA
from controlled_facts import generate,sha_cases


class FactCGReproductionContracts(unittest.TestCase):
    def test_pinned_model_and_author_instruction(self):
        self.assertEqual(len(FACTCG_SHA),40)
        self.assertEqual(FACTCG_ID,'yaxili96/FactCG-DeBERTa-v3-Large')
        self.assertIn('Choose your answer:',INSTRUCTION)
        self.assertEqual(prompt('source A','claim B'),
                         'source A\n\nChoose your answer: based on the paragraph above can we conclude that "claim B"?\n\nOPTIONS:\n- Yes\n- No\nI think the answer is ')

    def test_no_gold_inserted_into_model_prompt(self):
        case=generate()[0]
        shown=prompt(case['doc'],case['claim'])
        self.assertNotIn('"supported"',shown)
        self.assertNotIn('"state"',shown)
        self.assertIn(case['doc'],shown)
        self.assertIn(case['claim'],shown)

    def test_source_id_and_case_sha_contract(self):
        cases=generate()
        self.assertEqual(len(cases),120)
        self.assertEqual(len(sha_cases(cases)),64)
        self.assertEqual(sum(c['supported'] for c in cases),40)


if __name__=='__main__':
    unittest.main()
