import unittest
from budget_router import (allocation,experiment,link_weights,
                           ALLOCATORS,GLOBAL_BUDGET,SELECTORS,load,R25)


class RouterTests(unittest.TestCase):
    def test_budget_never_leaks_or_duplicates(self):
        docs=[0,1,2,3,4]
        orders={d:list(range(8)) for d in docs}
        weights={d:0 for d in docs}
        for name in ALLOCATORS:
            got=allocation(name,docs,orders,weights,19,GLOBAL_BUDGET)
            self.assertLessEqual(len(got),GLOBAL_BUDGET)
            self.assertEqual(len(got),len(set(got)),name)
            self.assertTrue(all(d in docs and sid in orders[d] for d,sid in got))

    def test_recycles_unused_capacity(self):
        docs=list(range(5))
        orders={0:[0,1,2,3,4],1:[0],2:[0,1,2],3:[0,1],4:[0,1,2,3]}
        weights={d:0 for d in docs}
        uniform=allocation('uniform2',docs,orders,weights,7)
        recycled=allocation('uniform_recycle',docs,orders,weights,7)
        self.assertLess(len(uniform),len(recycled))
        self.assertEqual(len(recycled),10)

    def test_short_realistic_candidate_pool_not_padded(self):
        docs=[0,1,2]
        orders={0:[0,1,2,3],1:[0,1,2],2:[0,1,2,3]}
        for name in ALLOCATORS:
            out=allocation(name,docs,orders,{0:1,1:0,2:0},19)
            self.assertLessEqual(len(out),GLOBAL_BUDGET)
            self.assertTrue(all(d in docs for d,_ in out))
        with self.assertRaises(ValueError):
            allocation('uniform2',[],orders,{},0)

    def test_counterfactual_random_is_reproducible(self):
        docs=list(range(5))
        orders={d:[0,1,2,3] for d in docs}
        a=allocation('random',docs,orders,{},31)
        b=allocation('random',docs,orders,{},31)
        self.assertEqual(a,b)

    def test_link_weight_uses_source_only(self):
        helper=load('cdg_r25_test57',R25)
        row={'context':[
            ['Founder',['Founder directed Film B.']],
            ['Film B',['A film.']],
            ['Film C',['No relationship.']],
            ['Film D',['An irrelevant note.']],
            ['Film E',['Another note.']]]}
        weights=link_weights(row,[0,1,2,3,4],helper)
        self.assertGreater(weights[0],weights[2])

    def test_integrated_two_partition_fixture(self):
        def make(id):
            return {'_id':id,'question':'Which film did Founder direct?',
                    'context':[
                        ['Founder',['Founder directed Film B.','Founder likes Film C.']],
                        ['Film B',['Film B was filmed.']],
                        ['Film C',['Film C is unrelated.']],
                        ['Film D',['Unrelated D.']],
                        ['Film E',['Unrelated E.']]],
                    'supporting_facts':[['Founder',0],['Film B',0]],
                    'answer':'Film B','type':'bridge'}
        result=experiment([make('a'),make('b')],split_size=1)
        self.assertEqual(len(result['results']),2*2*len(SELECTORS)*len(ALLOCATORS))
        for row in result['results']:
            self.assertEqual(row['n'],1)
            self.assertLessEqual(row['all_gold_sentences_recovered'],row['document_upper_bound'])
            self.assertLessEqual(row['mean_sentences_selected'],GLOBAL_BUDGET)

if __name__=='__main__':
    unittest.main()
