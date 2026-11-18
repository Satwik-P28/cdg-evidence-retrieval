import io,json,tarfile,unittest
from scifact_data_probe import inspect,fetch,parse,digests,UPSTREAM

def fake_tar():
    corpus=[{'doc_id':1,'title':'Example study','abstract':['A was measured.'],'structured':False}]
    dev=[{'id':100,'claim':'A was measured.',
          'evidence':{'1':[{'label':'SUPPORT','sentences':[0]}]},
          'cited_doc_ids':[1]}]
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w:gz') as tf:
        for name,records in [('data/corpus.jsonl',corpus),('data/claims_dev.jsonl',dev)]:
            data=('\n'.join(json.dumps(x) for x in records)+'\n').encode()
            info=tarfile.TarInfo(name)
            info.size=len(data)
            tf.addfile(info,io.BytesIO(data))
    return buf.getvalue()

class SciFactAuditTests(unittest.TestCase):
    def test_release_schema_and_hashes_without_network(self):
        raw=fake_tar()
        x=inspect(lambda url:raw)
        self.assertEqual(x['schema_counts']['claims_total'],1)
        self.assertEqual(x['schema_counts']['annotated_doc_claim_pairs'],1)
        self.assertEqual(x['schema_counts']['labels'],{'SUPPORT':1})
        self.assertEqual(x['archive']['sha256'],digests(raw)['sha256'])

    def test_corruption_and_wrong_mimetype_rejected(self):
        with self.assertRaises(ValueError):
            fetch(lambda url:b'not a tar.gz')

    def test_malformed_evidence_label_rejected(self):
        corpus={'data/corpus.jsonl':(json.dumps({'doc_id':1,'title':'Study','abstract':['x']})+'\n').encode()}
        corpus['data/claims_dev.jsonl']=(json.dumps({'id':1,'claim':'x','evidence':{'1':[{'label':'WRONG'}]}})+'\n').encode()
        with self.assertRaises(ValueError):
            parse(corpus)

if __name__=='__main__':
    unittest.main()
