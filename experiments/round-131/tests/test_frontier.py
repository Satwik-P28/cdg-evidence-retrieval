import os
from pathlib import Path
import pytest
from budget_archive import CONFIG,C,integrated_setup,append_policy,recover,fixture_origin
from vcdiff_screen import screen

@pytest.mark.parametrize("policy",CONFIG)
def test_budget(tmp_path,policy):
    db=integrated_setup(tmp_path/"x.sqlite",Path(os.environ["CDG_FTS_EXTENSION"]),{"fixture":True})
    base=" ".join(str(i*i) for i in range(500)).encode()
    sources=[base+str(i).encode() for i in range(12)]+[b"",b"short",base]
    for i,raw in enumerate(sources):
        append_policy(db,"a",raw,fixture_origin(raw,str(i)),policy)
    for i,raw in enumerate(sources):
        got,enc,dec,depth=recover(db,"a",i)
        assert got==raw and depth<=1
        assert 100*enc<=CONFIG[policy][2]*len(C.compress(raw))
        assert 100*dec<=CONFIG[policy][1]*len(raw)
    db.close()

def test_vcdiff():
    base=" ".join(str(i*i) for i in range(300)).encode()
    events=[("a",i,base+str(i).encode()) for i in range(5)]
    assert screen(events,1)["source_reads"]==5
