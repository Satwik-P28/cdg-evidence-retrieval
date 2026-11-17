import tempfile
import unittest
from pathlib import Path
from blind_temporal import (Index, read_data, question_window, select_fact,
                            evaluate, tokens)


class BlindRetrievalTests(unittest.TestCase):
    def test_calendar_windows_and_point_semantics(self):
        self.assertEqual(question_window('In February 2025 who?',True),
                         ('2025-02-01','2025-02-28'))
        self.assertEqual(question_window('In February 2025 who?',False),
                         ('2025-02-28','2025-02-28'))
        self.assertEqual(question_window('Between 2010 and 2012 who?',True),
                         ('2010-01-01','2012-12-31'))
        self.assertEqual(question_window('In 2018 who?',True),
                         ('2018-01-01','2018-12-31'))
        self.assertIsNone(question_window('who is the spouse?',True))

    def test_overlap_abstains(self):
        r={'before_object':{'label':'A','time_range':'2000-01-01 to ...'},
           'after_object':{'label':'B','time_range':'2020-01-01 to ...'}}
        answer,reason=select_fact(r,('2024-01-01','2024-12-31'),True)
        self.assertIsNone(answer)
        self.assertEqual(reason,'ambiguous')

    def test_bm25_and_exact_do_not_require_gold_id(self):
        rows=[{'key':1,'relation':'P26','upstream_id':5,'record':{
             'relation_label':'spouse','subject':{'label':'Alpha Beta'},
             'before_object':{'label':'Gamma','time_range':'2010-01-01 to 2020-01-01'},
             'after_object':{'label':'Delta','time_range':'2021-01-01 to ...'}}},
            {'key':2,'relation':'P26','upstream_id':99,'record':{
             'relation_label':'spouse','subject':{'label':'Other Person'},
             'before_object':{'label':'Delta','time_range':'2010-01-01 to 2020-01-01'},
             'after_object':{'label':'Gamma','time_range':'2021-01-01 to ...'}}}]
        index=Index(rows)
        try:
            question='In 2018 who was Alpha Beta married to?'
            self.assertEqual(index.choose(question,'exact'),1)
            self.assertIn(1,index.search(question,2))
            self.assertEqual(index.inspect(1)[0]['subject']['label'],'Alpha Beta')
            self.assertGreater(index.inspect(1)[1],0)
        finally:
            index.close()

    def test_source_hash_detects_tamper(self):
        rows=[{'key':1,'relation':'P35','upstream_id':1,'record':{
             'relation_label':'head of state','subject':{'label':'Place X'},
             'before_object':{'label':'A','time_range':'2000-01-01 to 2010-01-01'},
             'after_object':{'label':'B','time_range':'2011-01-01 to ...'}}}]
        index=Index(rows)
        try:
            sha,packed=index.payload[1]
            index.payload[1]=('0'*64,packed)
            with self.assertRaises(ValueError):
                index.inspect(1)
        finally:
            index.close()

    def test_existing_dataset_and_no_gold_based_retrieval(self):
        rows,qas=read_data()
        self.assertEqual(len(rows),91)
        self.assertEqual(len(qas),260)
        r=evaluate(rows,qas,k=5)
        self.assertEqual(r['questions'],260)
        self.assertLessEqual(r['methods']['exact_window']['correct'],260)
        self.assertGreater(r['topk_contains_gold'],0)

    def test_fts_input_is_parameterized(self):
        self.assertEqual(tokens('Who was the spouse of Jane Smith in 2020?'),
                         ['jane','smith'])
        rows,qa=read_data()
        index=Index(rows)
        try:
            index.search('who said \"drop table\" OR NOT?')
            self.assertEqual(len(index.rows),91)
        finally:
            index.close()

if __name__=='__main__':
    unittest.main()
