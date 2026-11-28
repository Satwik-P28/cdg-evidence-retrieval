import random,unittest,zlib
from partition import candidates,greedy,optimize,measure
class PartitionTests(unittest.TestCase):
    def test_dp_brute(self):
        rng=random.Random(195);enc=lambda x:zlib.compress(x,6)
        for _ in range(300):
            parts=[rng.randbytes(rng.randint(1,120)) for _ in range(rng.randint(1,9))]
            cap=rng.randint(20,500);p=rng.choice([0,1,4,16])
            spans,value=optimize(parts,cap,enc,p);best=None
            edges={(i,j):64*(z+64)+p*(j-i-1)*raw for i,j,raw,z in candidates(parts,cap,enc)}
            for mask in range(1<<(len(parts)-1)):
                ends=[i+1 for i in range(len(parts)-1) if mask>>i&1]+[len(parts)]
                i=0;score=0
                for j in ends:
                    if (i,j) not in edges:break
                    score+=edges[i,j];i=j
                else:best=score if best is None else min(best,score)
            self.assertEqual(value,best)
            stats=measure(parts,spans,enc)
            self.assertEqual(value,64*(stats["payload"]+64*stats["blocks"])+p*stats["excess"])
    def test_oversized(self):
        parts=[b"a"*4,b"b"*20,b"c"*3,b"d"*3]
        for spans in (greedy(parts,10),optimize(parts,10,zlib.compress)[0]):
            self.assertIn((1,2),spans)
            self.assertTrue(all(j==i+1 or sum(map(len,parts[i:j]))<=10 for i,j in spans))
