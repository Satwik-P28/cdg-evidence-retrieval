import copy,unittest
from cross_task_calibration import (
    SOURCE_SALT,TEST_SERIALIZATIONS,SCORES,TARGET_TRAIN_FPRS,
    choose_groups,flatten,source_for,prepare,risks,binary_confusion,
    load,R69,R70,R72
)


def source(sid,task,info):
    return {'source_id':sid,'task_type':task,'source_info':info}


def response(id,sid,text,split,positive=False):
    labels=[]
    if positive:
        start=text.index('Paris')
        labels=[{'start':start,'end':start+5,'text':'Paris',
                 'label_type':'Evident Conflict'}]
    return {'id':id,'source_id':sid,'response':text,'labels':labels,
            'quality':'good','split':split}


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.r69=load('r69_test_r74',R69)
        self.r70=load('r70_test_r74',R70)
        self.r72=load('r72_test_r74',R72)

    def test_structured_source_linearization_deterministic(self):
        obj={'name':'Café','hours':{'Tuesday':'9:00-17:00',
                                  'Monday':'9:00-18:00'},
             'takeout':False,'missing':None,'tags':['food','lunch']}
        first=list(flatten(obj))
        second=list(flatten(copy.deepcopy(obj)))
        self.assertEqual(first,second)
        self.assertEqual(first[0][0],'hours Monday')
        self.assertIn(('takeout','false'),first)
        self.assertFalse(any('missing' in x[0] for x in first))
        original=source('id','Data2txt',obj)
        natural=source_for(original,'field_linearized',self.r69)
        raw=source_for(original,'json',self.r69)
        self.assertIn('Café',natural)
        self.assertIn('Café',raw)
        self.assertNotEqual(raw,natural)

    def test_task_and_split_are_source_group_isolated(self):
        sources=[
            source(str(i),'QA' if i<4 else 'Data2txt',
                   {'passages':'The city is Berlin.'})
            for i in range(8)]
        responses=[
            response('r'+str(i),str(i),'The city is Berlin.',
                     'train' if i<4 else 'test') for i in range(8)]
        qa,qa_hash=choose_groups(responses,sources,'QA','train',2)
        other,test_hash=choose_groups(responses,sources,'Data2txt','test',2)
        self.assertEqual(len(qa),2)
        self.assertEqual(len(other),2)
        self.assertFalse({r['source_id'] for r in qa}.intersection(
            {r['source_id'] for r in other}))
        self.assertNotEqual(qa_hash,test_hash)

    def test_no_annotation_leakage_in_prompt_selection(self):
        info=source('id','QA',{'question':'Where did she go?',
                              'passages':'The inventor traveled to Berlin in 2016.'})
        a=response('r','id','She traveled to Paris.', 'train',positive=True)
        b=copy.deepcopy(a)
        b['labels']=[]
        pairs1,cases1,meta1=prepare([a],{'id':info},self.r69,
                                   self.r72,'json','QA_train')
        pairs2,cases2,meta2=prepare([b],{'id':info},self.r69,
                                   self.r72,'json','QA_train')
        self.assertEqual(pairs1,pairs2)
        self.assertEqual(cases1[0]['pair_indices'],cases2[0]['pair_indices'])
        self.assertNotEqual(cases1[0]['gold'],cases2[0]['gold'])
        self.assertEqual(meta1,meta2)

    def test_response_risk_aggregation_is_monotonic(self):
        base={
            'source_id':'s','response_id':'r','task':'QA',
            'suite':'QA_train','gold':1,'strict_gold':1,
            'lexical_warning':1,'pair_indices':[0,1,2]}
        result=risks([base],[.2,.8,.4])
        self.assertEqual(len(result),1)
        scores=result[0]['scores']
        self.assertAlmostEqual(scores['max_nonentail_risk'],.8)
        self.assertAlmostEqual(scores['mean_nonentail_risk'],
                               (.8+.2+.6)/3)
        self.assertAlmostEqual(scores['fraction_low_entail'],2/3)
        self.assertEqual(set(scores),set(SCORES))

    def test_confusion_stays_bound_to_original_human_labels(self):
        rec=[{'gold':1,'pred':True},{'gold':0,'pred':True},
             {'gold':0,'pred':False}]
        c=binary_confusion(rec,'pred')
        self.assertEqual(c,{'tp':1,'fp':1,'fn':0,'tn':1})
        self.assertEqual(TARGET_TRAIN_FPRS,(.10,.20))
        self.assertEqual(TEST_SERIALIZATIONS,('json','field_linearized'))
        self.assertTrue(SOURCE_SALT.startswith('CDG-R74'))

if __name__=='__main__':
    unittest.main()
