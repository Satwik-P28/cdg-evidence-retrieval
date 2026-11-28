import unittest,random
from selector import choose,totals
class Tests(unittest.TestCase):
    def test_shared_activation(self):
        m={1:(1,3),2:(1,4),3:(2,6)};b={1:(10,5),2:(6,3)}
        self.assertEqual(choose([1,2,3],m,b,7,10,"exact"),[1,2])
        self.assertEqual(totals([1,2],m,b),(7,10,5))
        self.assertEqual(choose([1,2,3],m,b,2,1,"exact"),[])
    def test_exhaustive(self):
        rng=random.Random(194)
        for _ in range(300):
            m={i:(i//3,rng.randint(1,30)) for i in range(10)}
            b={j:(sum(n for k,n in m.values() if k==j),10) for j in range(4)}
            r=list(m);rng.shuffle(r);c=rng.randrange(1,120);d=rng.randrange(1,180)
            def utility(ids):return sum(1000000//(r.index(i)+1) for i in ids)
            best=0
            for mask in range(1024):
                ids=[x for i,x in enumerate(r) if mask>>i&1]
                a,z,_=totals(ids,m,b)
                if a<=c and z<=d:best=max(best,utility(ids))
            for p in ("rank","context","shared","exact"):
                ids=choose(r,m,b,c,d,p);a,z,_=totals(ids,m,b)
                self.assertLessEqual(a,c);self.assertLessEqual(z,d)
                if p=="exact":self.assertEqual(utility(ids),best)
