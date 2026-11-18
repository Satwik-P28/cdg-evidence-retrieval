import unittest
from archived_detector import (
    load,R48,R69,R76,visible_prefix_end,substitute_source_text,
    materialize,r76_confusion,SUMMARY_MAX_WORDS
)


class ArchiveVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r48=load('r48_test78',R48)
        cls.r69=load('r69_test78',R69)
        cls.r76=load('r76_test78',R76)

    @staticmethod
    def src(task,text):
        if task=='QA':
            return {'source_id':'source','task_type':'QA',
                    'source_info':{'question':'Where?', 'passages':text}}
        return {'source_id':'source','task_type':'Summary','source_info':text}

    def test_utf8_summary_prefix_preserves_detector_context(self):
        raw='Émile 北京\t'+' '.join('mot'+str(i) for i in range(SUMMARY_MAX_WORDS+20))
        end=visible_prefix_end(raw,'Summary')
        self.assertLess(end,len(raw.encode('utf8')))
        self.assertEqual(len(raw.encode('utf8')[:end].decode().split()),
                         SUMMARY_MAX_WORDS)
        self.assertEqual(self.r76.assemble_context(
            self.src('Summary',raw),self.r69)[:2],
            self.r76.assemble_context(
                self.src('Summary',raw.encode('utf8')[:end].decode()),
                self.r69)[:2])

    def test_qa_full_source_and_question_exact(self):
        txt='Passage 1: Café in 北京.\nPassage 2: London is in the UK.'
        self.assertEqual(visible_prefix_end(txt,'QA'),len(txt.encode('utf8')))
        row=self.src('QA',txt)
        copy=substitute_source_text(row,txt)
        self.assertEqual(self.r76.assemble_context(copy,self.r69)[:2],
                         self.r76.assemble_context(row,self.r69)[:2])
        self.assertEqual(row['source_info']['passages'],txt)

    def test_two_archives_feed_identical_inputs(self):
        examples=[
            self.src('QA','Passage 1: Ada lived in Paris.\nPassage 2: Café!'),
            self.src('Summary',' '.join('w'+str(i) for i in range(600)))
        ]
        inputs=[self.r69.source_text(x).encode('utf8') for x in examples]
        for name in ('whole','gear512'):
            reader=self.r48.VersionedReader(inputs,name,'binary-zlib')
            for i,row in enumerate(examples):
                got,cost=materialize(reader,i,row,self.r69,self.r76)
                self.assertEqual(got,self.r76.assemble_context(
                    row,self.r69)[:2])
                self.assertTrue(0<cost['compressed_frame_bytes'])
                self.assertEqual(cost['source_bytes_requested'],len(inputs[i]))
                self.assertEqual(len(cost['source_digest_sha256']),64)

    def test_stale_generation_receipt_rejected(self):
        reader=self.r48.VersionedReader(
            [b'original',b'revised'],'whole','binary-zlib')
        with self.assertRaises(ValueError):
            reader.read(reader.receipt(0,0,3),pin_generation=1)
        with self.assertRaises(ValueError):
            visible_prefix_end('abc','Data2txt')

    def test_score_computes_response_and_character_separately(self):
        a=[False,True,False,True]
        b=[False,True,True,False]
        self.assertEqual(r76_confusion(a,b,False),
                         {'tp':1,'fp':1,'fn':1,'tn':1})
        self.assertEqual(r76_confusion(a,b,True),
                         {'tp':1,'fp':0,'fn':0,'tn':0})


if __name__=='__main__':
    unittest.main()
