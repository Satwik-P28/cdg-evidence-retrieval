import os,random
from pathlib import Path
import pytest
from blocked_positions import (CODECS,enc_dv,dec_dv,enc_vw,dec_vw,enc_bp,dec_bp,enc_stream,dec_stream,
    encode_block,parse_block,encode_dir,decode_dir,encode_term,build_blocks,BlockIndex,rank_blocked,
    shifted_count,f,h,tt,prepare,connect)

EXT=Path(os.environ["CDG_FTS_EXTENSION"])

def test_stream_codecs_round_trip():
    rng=random.Random(173)
    cases=[[],[0],[0,0,0],[1,2,3],[127,128,129],[0,255,256,65535,65536],
           [rng.randrange(0,1000) for _ in range(200)],[rng.randrange(0,2**20) for _ in range(64)]]
    for vals in cases:
        for codec in CODECS:
            tag,raw=enc_stream(vals,codec)
            assert list(dec_stream(tag,raw,len(vals)))==vals
    assert dec_dv(enc_dv(cases[4]),len(cases[4]))==cases[4]
    assert dec_vw(enc_vw(cases[4]),len(cases[4]))==cases[4]
    assert dec_bp(enc_bp(cases[4]),len(cases[4]))==cases[4]


def test_native_kernel_matches_python_fallback():
    import blocked_positions as bp
    rng=random.Random(1739)
    cases=[[],[0],[0,0],[1,2,3],[127,128,129],[rng.randrange(0,2**31) for _ in range(97)],
           [rng.randrange(0,4) for _ in range(1000)]]
    saved=bp.KERNEL
    try:
        for vals in cases:
            for codec in CODECS:
                tag,raw=enc_stream(vals,codec)
                bp.KERNEL=None;pure=list(bp.dec_stream(tag,raw,len(vals)))
                bp.KERNEL=saved
                if saved is not None:assert list(bp.dec_stream(tag,raw,len(vals)))==pure
                assert pure==vals
    finally:
        bp.KERNEL=saved

def test_stream_codec_errors():
    with pytest.raises(ValueError):enc_dv([-1])
    with pytest.raises(ValueError):enc_vw([2**32])
    with pytest.raises(ValueError):dec_dv(b"\x80",1)
    with pytest.raises(ValueError):dec_dv(b"\x01\x01",1)
    with pytest.raises(ValueError):dec_vw(b"",1)
    with pytest.raises(ValueError):dec_vw(b"\x05"+b"\x00"*5,1)
    with pytest.raises(ValueError):dec_bp(b"",1)
    with pytest.raises(ValueError):dec_bp(b"\x02\x00",5)
    with pytest.raises(ValueError):enc_stream([1],"nope")
    with pytest.raises(ValueError):dec_stream(9,b"",1)

def test_block_round_trip_all_codecs():
    rng=random.Random(1731)
    for codec in CODECS:
        for compress in (False,True):
            docs=[]
            for i in range(1,rng.randrange(2,40)):
                docs.append((i*3+1,sorted(rng.sample(range(500),rng.randrange(1,25)))))
            stored=encode_block(docs,codec,compress)
            full=parse_block(stored,docs[0][0],True)
            assert list(full["cids"])==[c for c,_ in docs]
            assert list(full["counts"])==[len(p) for _,p in docs]
            assert [full["positions"][c] for c,_ in docs]==[p for _,p in docs]
            lite=parse_block(stored,docs[0][0],False)
            assert list(lite["cids"])==list(full["cids"]) and list(lite["counts"])==list(full["counts"])
            assert lite["positions"] is None and lite["decoded"]<=full["decoded"]
            assert lite["activated"]==full["activated"]==len(stored)

def test_native_kernel_rejects_corrupt_streams():
    import blocked_positions as bp
    if bp.KERNEL is None:
        pytest.skip("native kernel not built")
    with pytest.raises(ValueError):bp.dec_stream(0,b"\x80",1)
    with pytest.raises(ValueError):bp.dec_stream(1,b"\x05"+b"\x00"*5,1)
    with pytest.raises(ValueError):bp.dec_stream(2,b"\x02\x00",5)


def test_block_errors():
    with pytest.raises(ValueError):encode_block([],  "dv",False)
    with pytest.raises(ValueError):encode_block([(5,[])],"dv",False)
    with pytest.raises(ValueError):encode_block([(5,[0]),(5,[1])],"dv",False)
    with pytest.raises(ValueError):encode_block([(5,[1,1])],"dv",False)
    good=encode_block([(7,[0,2])],"best",False)
    with pytest.raises(ValueError):parse_block(b"",7,True)
    with pytest.raises(ValueError):parse_block(b"\x07"+good[1:],7,True)
    with pytest.raises(ValueError):parse_block(good[:-1],7,True)

def test_directory_round_trip():
    rng=random.Random(1732)
    for _ in range(50):
        n=rng.randrange(1,40);firsts=sorted(rng.sample(range(10**5),n))
        offs=sorted(rng.sample(range(10**6),n));lens=[rng.randrange(1,500) for _ in range(n)]
        got=decode_dir(encode_dir(firsts,offs,lens))
        assert got==(firsts,offs,lens)
    with pytest.raises(ValueError):decode_dir(b"\x01\x00\x01\x00")

def test_shifted_count_exact_and_bound():
    rng=random.Random(1733)
    for _ in range(2000):
        seq=[rng.randrange(4) for _ in range(rng.randrange(1,80))]
        q=[rng.randrange(4) for _ in range(rng.randrange(2,9))]
        lists=[(i,[j for j,t in enumerate(seq) if t==x]) for i,x in enumerate(q)]
        exact=sum(seq[j:j+len(q)]==q for j in range(len(seq)-len(q)+1))
        assert shifted_count(lists,len(seq),len(q))==exact
        part=rng.sample(lists,rng.randrange(1,len(lists)+1))
        assert shifted_count(part,len(seq),len(q))>=exact

def _fixture(tmp_path,block,codec,compress,unified):
    ev=[("a",0,b"alpha beta x alpha beta alpha beta rare"),
        ("b",0,b"alpha alpha x beta alpha gamma"),
        ("a",1,b"alpha beta x alpha alpha gamma"),
        ("c",0,"CAF\u00c9 \u4e2d\u6587 alpha beta caf\u00e9".encode()),
        ("d",0,b""),
        ("e",0,b"beta beta beta alpha beta alpha beta"),
        ("c",1,b"alpha beta gamma alpha beta delta"),
        ("f",0,b"alpha alpha alpha alpha beta")]
    path=tmp_path/("db-%d-%s-%d-%d"%(block,codec,compress,unified))
    db,_=f.build(path,EXT,ev,"marginal",False)
    build_blocks(db,block,codec,compress,lexicon=unified)
    if not unified:tt.build_tape(db,path,ev,"frequency")
    db.commit();db.close()
    return ev,path

@pytest.mark.parametrize("block",[1,2,3,5])
@pytest.mark.parametrize("codec",["dv","best"])
@pytest.mark.parametrize("unified",[False,True])
def test_native_equivalence(tmp_path,block,codec,unified):
    ev,path=_fixture(tmp_path,block,codec,True,unified)
    db=connect(path,EXT);ids,_=tt.vocabulary(db)
    index=BlockIndex(db,ids,not unified)
    queries=[(("alpha beta",),"AND"),(("alpha alpha",),"AND"),(("alpha beta rare",),"AND"),
        (("alpha gamma beta",),"AND"),(("cafe \u4e2d\u6587","alpha beta"),"OR"),
        (("absent",),"AND"),(("beta",),"AND"),(("alpha alpha alpha",),"AND"),
        (("beta alpha beta",),"AND"),(("gamma",),"OR")]
    for cutoff in range(1,len(ev)+1):
        ref=h.active_oracle(ev,cutoff)
        for p,o in queries:
            hits,df,work=rank_blocked(db,p,o,prepare(db,cutoff),index)
            h.verify(hits,h.native(ref,p,o))
            assert len(df)==len(p)
        ref.close()
    db.close()

def test_candidate_aware_block_activation(tmp_path):
    ev=[]
    for i in range(40):
        if i==7:raw=b"alpha beta rare unique"
        elif i%2==0:raw=b"alpha filler filler alpha"
        else:raw=b"beta filler alpha filler beta"
        # distinct contents and articles: every revision is active and unique
        ev.append(("a%d"%i,0,raw+b" mark%d"%i))
    path=tmp_path/"activation"
    db,_=f.build(path,EXT,ev,"marginal",False)
    meta=build_blocks(db,4,"best",True)
    tt.build_tape(db,path,ev,"frequency")
    db.commit();db.close()
    assert meta["position_blocks"]==db_blocks(path)
    db=connect(path,EXT);ids,_=tt.vocabulary(db);index=BlockIndex(db,ids,True)
    hits,_,work=rank_blocked(db,("alpha beta rare",),"AND",prepare(db,40),index)
    total_blocks=db.execute("SELECT nblocks FROM term_blocks WHERE tid=?",(ids[b"rare"],)).fetchone()[0]
    assert total_blocks==1
    alpha=db.execute("SELECT nblocks FROM term_blocks WHERE tid=?",(ids[b"alpha"],)).fetchone()[0]
    assert alpha>1 and work["blocks_activated"]<=alpha
    assert work["blocks_activated"]<6 and work["source_reads"]==0
    assert work["position_exact"]>=1
    assert hits and hits[0][0]==8
    db.close()

def db_blocks(path):
    import sqlite3
    db=sqlite3.connect(path)
    n=db.execute("SELECT coalesce(sum(nblocks),0) FROM term_blocks").fetchone()[0]
    db.close();return n

def test_partial_coverage_still_exact(tmp_path):
    ev,path=_fixture(tmp_path,2,"dv",False,False)
    db=connect(path,EXT);ids,_=tt.vocabulary(db)
    db.execute("DELETE FROM term_blocks WHERE tid=?",(ids[b"beta"],))
    db.commit()
    index=BlockIndex(db,ids,True)
    for cutoff in range(1,len(ev)+1):
        ref=h.active_oracle(ev,cutoff)
        for p,o in [(("alpha beta",),"AND"),(("beta beta alpha",),"AND"),(("alpha beta gamma",),"AND")]:
            hits,_,work=rank_blocked(db,p,o,prepare(db,cutoff),index)
            h.verify(hits,h.native(ref,p,o))
        ref.close()
    assert work["source_reads"]>0
    db.close()

def test_encode_term_and_build_shape():
    postings=[(i*2+1,sorted({0,i,2*i+3})) for i in range(20)]
    enc=encode_term(postings,4,"best",True)
    assert enc["blocks"]==5 and enc["postings"]==20
    assert decode_dir(enc["dir"])==(enc["first_cids"],enc["offsets"],enc["lengths"])
    assert sum(enc["lengths"])==len(enc["body"])
    assert enc["offsets"]==[sum(enc["lengths"][:k]) for k in range(5)]
