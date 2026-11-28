"""R195: bounded byte partitions under identical original QASPER retrieval."""
import argparse,collections,hashlib,json,shutil,sqlite3,sys,tempfile,time
from pathlib import Path
import zstandard as zstd
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-194"))
from evidence_budget import (fetch_qasper,load_dev,document_bytes,base_fts_db,
    queries_for_original,independently_trained_samples,train_dictionaries,
    TRAIN_SHA,DEV_SHA,evaluate)
from partition import optimize,greedy
from paper_block_brotli import paper_id,MAX_BLOCK_BYTES

MODES=(("individual",0,0),("fixed4",0,0),("greedy2048",2048,0),
       ("dp2048",2048,0),("dp2048_penalty4",2048,4),
       ("greedy4096",4096,0),("dp4096",4096,0),("dp4096_penalty4",4096,4))

def build(path,base,docs,d,mode,cap,penalty):
    start=time.perf_counter_ns();shutil.copyfile(base,path)
    db=sqlite3.connect(str(path),isolation_level=None)
    db.execute("PRAGMA foreign_keys=ON")
    dd=zstd.ZstdCompressionDict(d["raw"]);assert dd.dict_id()==d["zstd_dict_id"]
    enc=zstd.ZstdCompressor(level=9,dict_data=dd).compress
    groups=collections.defaultdict(list)
    for rid,doc in enumerate(docs,1):groups[paper_id(doc)].append((rid,document_bytes(doc)))
    cnt=collections.Counter();bid=0
    db.execute("BEGIN IMMEDIATE")
    db.executescript("""
      DROP TABLE docs;
      CREATE TABLE source_blocks(
        block_id INTEGER PRIMARY KEY,paper_id TEXT NOT NULL,compressed BLOB NOT NULL,
        codec TEXT NOT NULL,sha256 BLOB NOT NULL CHECK(length(sha256)=32),
        utf8_len INTEGER NOT NULL,source_rows INTEGER NOT NULL,dict_id INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE source_receipts(
        rowid INTEGER PRIMARY KEY,doc_id TEXT UNIQUE NOT NULL,
        block_id INTEGER NOT NULL REFERENCES source_blocks(block_id),
        byte_offset INTEGER NOT NULL CHECK(byte_offset>=0),utf8_len INTEGER NOT NULL CHECK(utf8_len>=0),
        sha256 BLOB NOT NULL CHECK(length(sha256)=32));
      CREATE TABLE source_dictionaries(
        dict_id INTEGER PRIMARY KEY,payload BLOB NOT NULL,
        sha256 BLOB NOT NULL CHECK(length(sha256)=32),zstd_dict_id INTEGER NOT NULL);
    """)
    # executescript can implicitly commit a pending transaction. Start the
    # offline load transaction explicitly after schema creation.
    db.execute("BEGIN IMMEDIATE")
    db.execute("INSERT INTO source_dictionaries VALUES(1,?,?,?)",(d["raw"],d["sha256"],d["zstd_dict_id"]))
    t=time.perf_counter_ns()
    for pid,rows in groups.items():
        parts=[raw for _,raw in rows]
        if mode=="individual":spans=[(i,i+1) for i in range(len(parts))]
        elif mode=="fixed4":spans=[(i,min(i+4,len(parts))) for i in range(0,len(parts),4)]
        elif mode.startswith("greedy"):spans=greedy(parts,cap)
        else:spans,_=optimize(parts,cap,enc,penalty)
        pos=0
        for i,j in spans:
            assert i==pos and i<j<=len(parts);pos=j
            raw=b"".join(parts[i:j]);n=len(raw)
            assert n<=MAX_BLOCK_BYTES
            if cap:assert n<=cap or j==i+1
            blob=enc(raw);bid+=1
            db.execute("INSERT INTO source_blocks VALUES(?,?,?,?,?,?,?,1)",
                (bid,pid,blob,"zstd9-dictionary",hashlib.sha256(raw).digest(),n,j-i))
            off=0
            for rid,part in rows[i:j]:
                db.execute("INSERT INTO source_receipts VALUES(?,?,?,?,?,?)",
                    (rid,str(docs[rid-1]["doc_id"]),bid,off,len(part),hashlib.sha256(part).digest()))
                off+=len(part)
            assert off==n
            cnt["payload_bytes"]+=len(blob);cnt["source_bytes"]+=n;cnt["uniform_excess_decode_bytes"]+=(j-i-1)*n
            cnt["max_decoded_block_bytes"]=max(cnt["max_decoded_block_bytes"],n)
            cnt["oversized_singletons"]+=int(bool(cap) and n>cap)
        assert pos==len(parts)
    cnt["blocks"]=bid;cnt["partition_and_insert_us"]=(time.perf_counter_ns()-t)/1000
    db.execute("COMMIT");db.execute("VACUUM")
    assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    assert not db.execute("PRAGMA foreign_key_check").fetchone()
    cnt["build_us"]=(time.perf_counter_ns()-start)/1000
    return db,dict(cnt)

def main():
    p=argparse.ArgumentParser();p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    src=fetch_qasper();assert src["train"]["sha256"]==TRAIN_SHA and src["dev"]["sha256"]==DEV_SHA
    train=src["train"]["data"];dev=src["dev"]["data"];assert not set(train)&set(dev)
    docs,cases,cohort=load_dev(dev);assert len(docs)==13266 and len(cases)==1005
    samples,training=independently_trained_samples(train);d=train_dictionaries(samples,(65536,))[65536]
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp);base=folder/"fts.sqlite";db=base_fts_db(base,docs)
        ranked=queries_for_original(docs,cases,db);db.close()
        layouts=[]
        for mode,cap,penalty in MODES:
            path=folder/(mode+".sqlite");db,stats=build(path,base,docs,d,mode,cap,penalty)
            assert queries_for_original(docs,cases,db)==ranked
            result=evaluate(db,docs,cases,ranked)
            row=dict(mode=mode,cap=cap,penalty=penalty,sqlite_bytes=path.stat().st_size,**stats,**result)
            layouts.append(row);db.close();path.unlink();print("ARM_JSON="+json.dumps(row),flush=True)
    out=dict(round=195,train_sha256=TRAIN_SHA,dev_sha256=DEV_SHA,dict_sha256=d["sha256"].hex(),
        training=training,cohort=cohort,source_docs=len(docs),questions=len(cases),layouts=layouts,
        limitations=["same reused dev corpus, known article scope, same fixed top10 rank candidates",
        "byte-cap exceptions only for indivisible oversized source paragraphs",
        "dynamic program optimal only for contiguous candidate blocks and proxy cost, not actual SQLite pages",
        "uniform per-source decode penalty is label-free and not learned access telemetry",
        "source/context UTF8 and raw decompression bytes, not prompt token or physical IO budgets",
        "no actual equal persistent-byte constraint; report measured layouts, not prospective best policy",
        "no answer generation or transaction append claim"])
    a.out.write_text(json.dumps(out,indent=2)+"\n");print("RESULT_JSON="+json.dumps(out),flush=True)
if __name__=="__main__":main()
