import os,struct
from pathlib import Path
from token_equivalence import connect,build,rank,h
EXT=Path(os.environ["CDG_FTS_EXTENSION"])
def unpack(blob):
    out=[];i=0
    while i<len(blob):
        n=struct.unpack_from(">I",blob,i)[0];i+=4;out.append(blob[i:i+n].decode());i+=n
    assert i==len(blob)
    return out
def test_native_vocab(tmp_path):
    db=connect(tmp_path/"vocab.sqlite",EXT)
    db.execute("CREATE VIRTUAL TABLE docs USING fts5(body,content='')")
    db.execute("CREATE VIRTUAL TABLE vocab USING fts5vocab(docs,'instance')")
    texts=["", "CAFÉ cafe\u0301 naïve", "Hello, WORLD!", "中文 한글 русский", "alpha\0beta", "one one two", "a_b-c"]
    for g,t in enumerate(texts,1):
        db.execute("INSERT INTO docs(rowid,body) VALUES(?,?)",(g,t))
        got=unpack(db.execute("SELECT cdg_token_stream(?)",(t,)).fetchone()[0])
        expected=[x for x, in db.execute("SELECT term FROM vocab WHERE doc=? ORDER BY offset",(g,))]
        assert got==expected
    db.close()
def test_token_equivalence_keeps_identity(tmp_path):
    ev=[("a",0,b"Hello world"),("b",0,b"HELLO, WORLD!"),("c",0,b"world hello"),("a",1,b"hello other")]
    bodies=[]
    for mode in ("revision","raw","token"):
        db,size=build(tmp_path/mode,EXT,ev,mode)
        assert size["index_rows"]==(3 if mode=="token" else 4)
        sig=[]
        for c in (2,3,4):
            ref=h.active_oracle(ev,c)
            for p,o in [(("hello world",),"AND"),(("hello","world"),"OR"),(("world hello",),"AND")]:
                hits,df=rank(db,p,o,c);h.verify(hits,h.native(ref,p,o));sig.append((hits,df))
            ref.close()
        bodies.append(sig);db.close()
    assert bodies[0]==bodies[1]==bodies[2]
