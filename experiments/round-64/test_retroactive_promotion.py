import unittest
from retroactive_promotion import (StreamingArchive,experiment,load,
                                   THRESHOLD,POLICIES,R46,R47,R63)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.r46=load('cdg46_test64',R46)
        self.r47=load('cdg47_test64',R47)
        self.r63=load('cdg63_test64',R63)
        self.one=(b'Documentation header for this project. '*100)+b'first version!'
        self.two=(b'Documentation header for this project. '*100)+b'second version.'
        self.unrelated=b'This is a genuinely distinct tiny source, without prior substrings.'
        self.docs=[('history',self.one),('history',self.two),
                   ('independent',self.unrelated)]

    def make(self,docs=None,policy='threshold_migration'):
        return StreamingArchive(
            self.docs if docs is None else docs,policy,
            self.r46.frame,self.r47,self.r63.windows)

    def test_related_arrival_migrates_prior_without_byte_loss(self):
        archive=self.make()
        self.assertGreaterEqual(archive.migrated_prior_sources,1)
        self.assertEqual(archive.assignments[:2],['gear512','gear512'])
        self.assertEqual(archive.assignments[2],'whole')
        for i,(_,raw) in enumerate(self.docs):
            self.assertEqual(archive.read(i,0,len(raw))[0],raw)
            self.assertEqual(archive.read(i,3,min(len(raw),100))[0],
                             raw[3:min(len(raw),100)])
        self.assertGreater(archive.payload_write_bytes,0)
        self.assertGreater(archive.recompression_source_plain_bytes,0)
        self.assertEqual(set(archive.payloads),set(archive.references))
        self.assertTrue(all(ref>0 for ref in archive.references.values()))

    def test_without_migration_first_source_stays_whole(self):
        controlled=self.make(policy='threshold_nomigration')
        migrated=self.make()
        self.assertEqual(controlled.assignments[0],'whole')
        self.assertEqual(migrated.assignments[0],'gear512')
        self.assertEqual(controlled.migrated_prior_sources,0)
        self.assertGreater(migrated.migrated_prior_sources,0)

    def test_label_blind_policy(self):
        mutated=[('independent' if typ=='history' else 'history',raw)
                 for typ,raw in self.docs]
        first=self.make(self.docs)
        second=self.make(mutated)
        self.assertEqual(first.assignments,second.assignments)
        self.assertEqual(first.archive_bytes(),second.archive_bytes())
        self.assertEqual(first.scores,second.scores)

    def test_no_false_promotion_of_short_dissimilar_docs(self):
        docs=[('history',b'first unique source.'),
              ('history',b'second, dissimilar source.'),
              ('independent',b'third unlike everything else.')]
        obj=self.make(docs)
        self.assertEqual(obj.migrated_prior_sources,0)
        self.assertEqual(obj.assignments,['whole']*3)
        for i,(_,raw) in enumerate(docs):
            self.assertEqual(obj.read(i,0,len(raw))[0],raw)

    def test_corruption_and_invalid_spans_rejected(self):
        obj=self.make()
        with self.assertRaises(ValueError):obj.read(0,-1,10)
        index=next(iter(obj.payloads))
        obj.payloads[index]=b'bad zlib contents'
        with self.assertRaises(Exception):obj.read(0,0,len(self.one))

    def test_small_full_matrix_and_total_costs(self):
        entries={
            'ruff':[{'data':self.one,'sha256':'1'*64},
                    {'data':self.two,'sha256':'2'*64}],
            'vllm':[{'data':b'vllm header '*100+b'a','sha256':'3'*64},
                    {'data':b'vllm header '*100+b'b','sha256':'4'*64}]}
        independent=[('independent',b'independent note '+str(i).encode())
                     for i in range(512)]
        import retroactive_promotion as m
        saved=m.INDEPENDENT_COUNTS
        m.INDEPENDENT_COUNTS=(0,128)
        try:
            result=experiment(entries,independent)
        finally:
            m.INDEPENDENT_COUNTS=saved
        self.assertEqual(len(result['scenarios']),4)
        for row in result['scenarios']:
            self.assertEqual(set(row['methods']),set(POLICIES)|{'R58_ungated'})
            for method in POLICIES:
                metric=row['methods'][method]
                self.assertEqual(metric['source_readback_count'],
                                 row['history_versions']+row['independent_sources'])
                self.assertGreater(metric['archive_bytes'],0)
                self.assertGreaterEqual(metric['migration_count'],0)
                self.assertGreaterEqual(metric['manifest_rewrite_upper_bound_bytes'],
                                        metric['archive_bytes']-metric['payload_write_bytes'])

if __name__=='__main__':unittest.main()
