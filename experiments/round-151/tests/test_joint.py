import os,sys,subprocess
from pathlib import Path
import pytest
import joint_archive as j
from joint_archive import tp,pv,bv,h
EXT=Path(os.environ["CDG_FTS_EXTENSION"])

@pytest.mark.parametrize("mode,stage",[(m,s) for m,stages in [("new",tp.STAGES),("reuse",("reuse","source","index","ledger","meta","commit"))] for s in stages])
def test_atomic_index(tmp_path,mode,stage):
    path=tmp_path/"archive";db=j.setup(path,EXT,{},True)
    fd=os.open(tp.side(path),os.O_RDWR);raw=b"old evidence "*100
    j.append(db,fd,"a",raw,tp.fixture(raw,"first"),"snapshot",quotient=True)
    reader=pv.connect(path,EXT);reader.execute("BEGIN")
    manifest,roots,_=bv.prefix_set(reader,[1]);old=j.issue(reader,fd,("old",),"AND",1,manifest,roots[1],True)
    db.close()
    p=subprocess.run([sys.executable,str(Path(j.__file__).resolve()),"--crash",str(path),str(EXT),stage,mode],capture_output=True,timeout=60)
    assert p.returncode==77,p.stderr
    db=pv.connect(path,EXT);tp.reconcile(db,fd);db.execute("BEGIN")
    n=2 if stage=="commit" else 1
    assert j.audit(db,fd,True)==n and j.batch(db,fd,[old],True)==1
    db.rollback();j.append(db,fd,"c",raw,tp.fixture(raw,"retry"),"snapshot",quotient=True)
    assert j.batch(reader,fd,[old],True)==1
    reader.rollback();reader.close();db.execute("BEGIN");assert j.audit(db,fd,True)==n+1
    db.rollback();db.close();os.close(fd)

def test_identical_receipts(tmp_path):
    ev=[("a",0,b"alpha beta "*100),("b",0,b"alpha beta "*100),("a",1,b"alpha gamma "*100),("c",0,b"alpha gamma "*100)]
    signatures=[]
    for q in (False,True):
        path=tmp_path/str(q);db=j.setup(path,EXT,{},q);fd=os.open(tp.side(path),os.O_RDWR)
        for g,(a,i,raw) in enumerate(ev,1):
            assert j.append(db,fd,a,raw,tp.fixture(raw,str(g)),"marginal",quotient=q)==(g,i)
        db.execute("BEGIN");assert j.audit(db,fd,q)==len(ev)
        sig=[]
        for c in range(1,len(ev)+1):
            ref=h.active_oracle(ev,c);manifest,roots,_=bv.prefix_set(db,[c])
            for p,o in [(("alpha beta",),"AND"),(("alpha","gamma"),"OR")]:
                body,digest=j.issue(db,fd,p,o,c,manifest,roots[c],q)
                h.verify([(v["g"],float.fromhex(v["score_hex"])) for v in body["ranking"]["hits"]],h.native(ref,p,o))
                sig.append((body,digest))
            ref.close()
        signatures.append(sig);db.rollback();db.close();os.close(fd)
    assert signatures[0]==signatures[1]
