from query_materialization import choose_under_budget,fractional_bound
from collections import Counter
import itertools,random

def test_budget_and_oracle():
    rng=random.Random(139)
    for _ in range(100):
        items={g:(rng.randrange(1,20),rng.randrange(1,50)) for g in range(8)}
        counts=Counter({g:rng.randrange(4) for g in items});budget=rng.randrange(1,50)
        selected,spent=choose_under_budget(items,lambda g:counts[g]*items[g][1]/items[g][0],budget)
        assert spent==sum(items[g][0] for g in selected)<=budget
        best=max(sum(counts[g]*items[g][1] for g in ss)
                 for n in range(9) for ss in itertools.combinations(items,n)
                 if sum(items[g][0] for g in ss)<=budget)
        assert sum(counts[g]*items[g][1] for g in selected)<=best<=fractional_bound(items,counts,budget)+1e-8
