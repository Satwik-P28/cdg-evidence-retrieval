import unittest
from source_only_bound import (
    source_only_ceiling,group_stats,archive_costs,QA_TEST_GROUP_LIMIT,
    dynamic,R69,
)


def source(sid,text):
    return {'source_id':sid,'task_type':'QA',
            'source_info':{'question':'What city?','passages':text}}


def reply(id,sid,text,flag=False,implicit=False):
    labels=[]
    if flag:
        token=text.index('Paris')
        labels=[{'start':token,'end':token+5,'text':'Paris',
                 'label_type':'Evident Conflict','implicit_true':implicit}]
    return {'id':id,'source_id':sid,'split':'test','quality':'good',
            'response':text,'labels':labels}


class SourceOnlyTests(unittest.TestCase):
    def test_mixed_source_yields_irreducible_errors(self):
        group={'same_source':[
            {'human_unsupported':True,'strict_unsupported':True,'quality_good':True},
            {'human_unsupported':False,'strict_unsupported':False,'quality_good':True},
            {'human_unsupported':False,'strict_unsupported':False,'quality_good':True},
            {'human_unsupported':True,'strict_unsupported':True,'quality_good':True},
        ]}
        report=source_only_ceiling(group)
        self.assertEqual(report['responses'],4)
        self.assertEqual(report['mixed_truth_source_groups'],1)
        self.assertEqual(report['unavoidable_source_only_errors'],2)
        self.assertEqual(report['source_only_oracle_correct'],2)
        self.assertEqual(report['conditional_source_only_oracle_accuracy'],.5)

    def test_pure_source_group_has_no_oracle_errors(self):
        cases={'s':[{'human_unsupported':False,'strict_unsupported':False,
                     'quality_good':True} for _ in range(3)]}
        result=source_only_ceiling(cases)
        self.assertEqual(result['unavoidable_source_only_errors'],0)
        self.assertEqual(result['mixed_truth_source_groups'],0)
        self.assertEqual(result['conditional_source_only_oracle_accuracy'],1)

    def test_label_stratification_does_not_change_source_bytes(self):
        s=[source('s','The artist lived in Berlin in 1998.\nAnd then traveled.') ]
        a=reply('a','s','The artist lived in Paris.',True)
        b=reply('b','s','The artist lived in Berlin.',False)
        c=reply('c','s','The artist lived in Paris.',True,True)
        groups,mapping,faults=group_stats([a,b,c],s)
        self.assertFalse(faults)
        self.assertEqual(len(groups['s']),3)
        strict=source_only_ceiling(groups,'strict_unsupported')
        general=source_only_ceiling(groups,'human_unsupported')
        self.assertEqual(strict['human_positive_responses'],1)
        self.assertEqual(general['human_positive_responses'],2)

    def test_fts_exact_archived_source_materialization(self):
        r={
            'a':source('a','The inventor lived in Berlin.\nThe painter lived in Rome.'),
            'b':source('b','The inventor lived in Paris.\nThe author lived in Athens.'),
        }
        stats=archive_costs(r,set(r))
        self.assertEqual(stats['source_count'],2)
        self.assertEqual(stats['exact_full_source_receipts_verified'],4)
        self.assertEqual(stats['exact_source_span_reads_verified'],8)
        self.assertGreater(stats['fts_index_bytes'],0)
        self.assertGreater(stats['archive_bytes']['whole_zlib'],0)
        self.assertGreater(stats['archive_bytes']['gear512'],0)

    def test_benchmark_domain_limit_is_declared(self):
        self.assertEqual(QA_TEST_GROUP_LIMIT,150)
        self.assertEqual(len(dynamic('r69_71_unit',R69).REVISION),40)


if __name__=='__main__':unittest.main()
