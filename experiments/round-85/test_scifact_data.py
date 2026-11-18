import hashlib
import io
import json
import tarfile
import unittest
from scifact_data import decode_release,extract_pairs,selection_key


class SciFactDataContractTests(unittest.TestCase):
    def test_official_jsonl_tar_parser(self):
        fake={
          'corpus.jsonl':[{'doc_id':1,'title':'A','abstract':['Fact one.']}],
          'claims_train.jsonl':[{'id':1,'claim':'Fact one.','evidence':{'1':[{'label':'SUPPORT','sentences':[0]}]}}],
          'claims_dev.jsonl':[{'id':2,'claim':'Fact two.','evidence':{'1':[{'label':'CONTRADICT','sentences':[0]}]}}],
        }
        buff=io.BytesIO()
        with tarfile.open(fileobj=buff,mode='w:gz') as tf:
            for filename,rows in fake.items():
                raw=('\n'.join(json.dumps(x) for x in rows)+'\n').encode()
                obj=tarfile.TarInfo('data/'+filename)
                obj.size=len(raw)
                tf.addfile(obj,io.BytesIO(raw))
        result,sha=decode_release(buff.getvalue(),expected_sha=None)
        with self.assertRaises(AssertionError):
            decode_release(buff.getvalue(),expected_sha='0'*64)
        self.assertEqual(set(result),set(fake))
        self.assertEqual(result['claims_dev.jsonl'][0]['id'],2)
        self.assertEqual(sha,hashlib.sha256(buff.getvalue()).hexdigest())

    def test_evidence_and_rationale_label_mapping(self):
        docs={'17':{'doc_id':17,'title':'Test paper',
                    'abstract':['A is not B.','C follows D.']}}
        rows=[{'id':3,'claim':'C follows D.','evidence':{'17':[
            {'label':'SUPPORT','sentences':[1]}]}}]
        extracted,invalid=extract_pairs(rows,docs,'train')
        self.assertFalse(invalid)
        self.assertEqual(len(extracted),1)
        self.assertEqual(extracted[0]['gold'],1)
        self.assertEqual(extracted[0]['rationale'],'C follows D.')
        self.assertIn('Test paper',extracted[0]['doc'])

    def test_no_ambiguous_or_invalid_rationale_promotion(self):
        docs={'17':{'doc_id':17,'title':'Title','abstract':['Actual statement.']}}
        rows=[
            {'id':1,'claim':'claim','evidence':{'17':[{'label':'SUPPORT','sentences':[0]},
                                                     {'label':'CONTRADICT','sentences':[0]}]}},
            {'id':2,'claim':'claim','evidence':{'17':[{'label':'SUPPORT','sentences':[13]}]}},
            {'id':3,'claim':'claim','evidence':{'19':[{'label':'SUPPORT','sentences':[0]}]}},
        ]
        extracted,invalid=extract_pairs(rows,docs,'dev')
        self.assertEqual(len(extracted),0)
        self.assertEqual(invalid['ambiguous_label'],1)
        self.assertEqual(invalid['invalid_rationale'],1)
        self.assertEqual(invalid['missing_abstract'],1)

    def test_sha_selection_is_order_and_label_independent(self):
        a={'key':'train:10:100:SUPPORT','gold':1}
        b={'key':'train:10:100:SUPPORT','gold':0}
        self.assertEqual(selection_key(a),selection_key(b))
        self.assertEqual(len(selection_key(a)),64)


if __name__=='__main__':
    unittest.main()
