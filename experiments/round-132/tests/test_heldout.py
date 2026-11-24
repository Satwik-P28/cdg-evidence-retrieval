import os
from pathlib import Path
import pytest
from heldout_archive import POLICIES,CONFIG,DEPTHS,C,integrated_setup,append_policy,recover,fixture_origin,eligible

@pytest.mark.parametrize("policy",POLICIES)
def test_policy(tmp_path,policy):
    db=integrated_setup(tmp_path/"x.sqlite",Path(os.environ["CDG_FTS_EXTENSION"]),{"fixture":True})
    base=" ".join(str(i*i) for i in range(500)).encode()
    sources=[base+str(i).encode() for i in range(12)]+[b"",b"short",base]
    for i,raw in enumerate(sources):
        append_policy(db,"a",raw,fixture_origin(raw,str(i)),policy)
    for i,raw in enumerate(sources):
        got,enc,dec,depth=recover(db,"a",i)
        assert got==raw and depth<=DEPTHS[policy]
        if policy in CONFIG:
            assert 100*enc<=CONFIG[policy][2]*len(C.compress(raw))
            assert 100*dec<=CONFIG[policy][1]*len(raw)
    db.close()

def test_eligibility():
    assert eligible("Documentation/git-add.txt","gitdocs")
    assert not eligible("Documentation/RelNotes/2.47.txt","gitdocs")
    assert eligible("content/en/docs/tasks/test.md","k8sdocs")
    assert not eligible("content/en/docs/tasks/_index.md","k8sdocs")
