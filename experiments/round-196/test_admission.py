import random,unittest
from admission import priority,subset,fit_prefix

class AdmissionTests(unittest.TestCase):
    def test_mapping(self):
        docs=[dict(doc_id=f"p{i//3}|0|{i}") for i in range(6)]
        cases=[dict(paper="p0",gold_rowids={1,2,3}),dict(paper="p1",gold_rowids={4,5}),dict(paper="none",gold_rowids=set())]
        chosen,scoped=subset(docs,cases,[0,3,1,2,4,5],2)
        self.assertEqual([d["doc_id"] for d in chosen],["p0|0|0","p1|0|3"])
        self.assertEqual(scoped[0]["gold_rowids"],{1,-2,-3})
        self.assertEqual(scoped[1]["gold_rowids"],{2,-5})
        self.assertEqual((scoped[2]["row_start"],scoped[2]["row_end"]),(1,0))
    def test_balanced(self):
        docs=[dict(doc_id=f"p{i//3}|0|{i}") for i in range(15)]
        order=priority(docs,196,"balanced")
        self.assertEqual(len({docs[i]["doc_id"].split("|")[0] for i in order[:5]}),5)
        self.assertEqual(sorted(order),list(range(15)))
        self.assertEqual(priority(docs,196,"balanced"),order)
    def test_budgets(self):
        rng=random.Random(196)
        for _ in range(500):
            # Deliberately nonmonotone physical cost model, but first fits.
            n=rng.randrange(10,150);size={i:100+i*10+rng.randrange(-50,51) for i in range(1,n+1)}
            cap=rng.randrange(max(size[1],200),max(size.values())+100)
            k,z=fit_prefix(n,cap,size.__getitem__)
            self.assertEqual(z,size[k]);self.assertLessEqual(z,cap)
        self.assertEqual(fit_prefix(100,100,lambda n:n),(100,100))
