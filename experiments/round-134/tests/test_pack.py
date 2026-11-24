from pack_archive import prepare_objects,make_pack,path_cost,Reader,oid
from pathlib import Path

def test_native_pack(tmp_path):
    base=" ".join(str(i*i) for i in range(1000)).encode()
    events=[("a",i,base+str(i).encode()) for i in range(6)]+[("b",0,base+b"0")]
    source,unique=prepare_objects(tmp_path,events)
    assert len(unique)==6
    repo,rows,stats=make_pack(tmp_path,source,unique,1)
    assert stats["max_depth"]<=1
    for a,i,raw in events:
        assert path_cost(oid(raw),rows,unique)[1]>=len(raw)
