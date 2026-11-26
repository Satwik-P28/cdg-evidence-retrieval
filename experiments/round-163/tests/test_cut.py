import itertools,random
from dictionary_facilities import cut_clients

def test_cut_against_bruteforce():
    rng=random.Random(163)
    for _ in range(64):
        weights={str(i):rng.randrange(1,25) for i in range(6)}
        masks={n:rng.randrange(16) for n in weights};penalty=rng.randrange(15)
        selected,gain=cut_clients(weights,masks,penalty)
        best=0
        for k in range(7):
            for ns in itertools.combinations(weights,k):
                u=0
                for n in ns:u|=masks[n]
                best=max(best,sum(weights[n] for n in ns)-penalty*u.bit_count())
        assert gain==best
        assert set(selected)<=set(weights)

def test_shared_cost_changes_choice():
    # Individually unprofitable, together profitable due to shared activation.
    assert cut_clients({"a":6,"b":6},{"a":1,"b":1},10)==(["a","b"],2)
    assert cut_clients({"a":6,"b":6},{"a":1,"b":2},10)==([],0)
