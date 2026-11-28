"""R196: persistent SQLite bytes, source context and block decode caps."""
import argparse,collections,json,sqlite3,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-195"))
from bounded_layout import (build,fetch_qasper,load_dev,document_bytes,
    base_fts_db,queries_for_original,independently_trained_samples,
    train_dictionaries,TRAIN_SHA,DEV_SHA)
from train_only_zstd_dictionary import base_archive,make_variant,OriginalSourceReader
from joint_group_dictionary import GroupSourceReader
from selector import choose,totals
from admission import priority,subset,fit_prefix

CAPS=(6*1024*1024,8*1024*1024)
BUDGETS=((2048,4096),(4096,8192),(4096,32768))
MODES=(("compact_individual",0,0),("individual",0,0),("fixed4",0,0),
       ("greedy2048",2048,0),("dp4096_penalty4",4096,4),("dp4096",4096,0))

def materialize(folder,docs,d,mode,block_cap,penalty):
    base=folder/"base.sqlite";path=folder/"archive.sqlite"
    assert not base.exists() and not path.exists()
    if mode=="compact_individual":
        db=base_archive(base,docs);db.close()
        db,stats=make_variant(path,base,docs,"zstd9_dict65536",{65536:d})
    else:
        db=base_fts_db(base,docs);db.close()
        db,stats=build(path,base,docs,d,mode,block_cap,penalty)
    base.unlink();db.close()
    return path,stats

def evaluate(path,docs,cases,compact):
    db=sqlite3.connect(path)
    try:
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        ranked=queries_for_original(docs,cases,db)
        if compact:
            reader=OriginalSourceReader(db)
            meta={r:(r,n) for r,n in db.execute("SELECT rowid,utf8_len FROM docs")}
            blocks={r:(n,z) for r,n,z in db.execute("SELECT rowid,utf8_len,length(compressed) FROM docs")}
            def read(r,cache):
                raw=reader.read(r,str(docs[r-1]["doc_id"]))
                return raw,len(raw)
        else:
            reader=GroupSourceReader(db)
            meta={r:(b,n) for r,b,n in db.execute("SELECT rowid,block_id,utf8_len FROM source_receipts")}
            blocks={b:(n,z) for b,n,z in db.execute("SELECT block_id,utf8_len,length(compressed) FROM source_blocks")}
            def read(r,cache):
                x=reader.read(r,cache);assert x["doc_id"]==str(docs[r-1]["doc_id"])
                return x["source_bytes"],x["decoded_block_bytes"]
        assert len(meta)==len(docs)
        # Bounded audit memory: one source at a time, no reuse across audit reads.
        for r,doc in enumerate(docs,1):
            raw,_=read(r,{})
            assert raw==document_bytes(doc)
        rows=[]
        for context,decode in BUDGETS:
            cnt=collections.Counter();bits=[]
            for c in cases:
                rs=ranked[c["id"]];assert all(c["row_start"]<=r<=c["row_end"] for r in rs)
                ids=choose(rs,meta,blocks,context,decode,"rank")
                cb,dbb,encoded=totals(ids,meta,blocks)
                assert cb<=context and dbb<=decode
                cache={};actual=0
                for r in ids:
                    raw,n=read(r,cache);assert raw==document_bytes(docs[r-1]);actual+=n
                assert actual==dbb
                cnt["questions"]+=1;cnt["empty"]+=not ids
                cnt["context_bytes"]+=cb;cnt["decoded_bytes"]+=dbb
                cnt["activated_payload_bytes"]+=encoded;cnt["source_checks"]+=len(ids)
                gold=c["gold_rowids"]
                if gold:
                    hits=len(gold&set(ids));available=sum(r>0 for r in gold)
                    cnt["eligible"]+=1;cnt["hits"]+=bool(hits)
                    cnt["gold_found"]+=hits;cnt["gold_total"]+=len(gold)
                    cnt["complete_union"]+=hits==len(gold)
                    cnt["any_gold_available"]+=available>0
                    cnt["all_gold_available"]+=available==len(gold)
                    cnt["top10_gold"]+=bool(gold&set(rs))
                    bits.append(int(bool(hits)))
            assert cnt["eligible"]==888
            rows.append(dict(context_budget=context,decode_budget=decode,**dict(cnt),eligible_hit_bits=bits))
        return dict(all_source_checks=len(docs),papers=len({str(d["doc_id"]).rsplit("|",2)[0] for d in docs}),rows=rows)
    finally:db.close()

def run(docs,cases,d,seed,policy,folder):
    order=priority(docs,seed,policy);results=[]
    for mode,block_cap,penalty in MODES:
        sizes={};start=time.perf_counter()
        def probe(n):
            if n not in sizes:
                chosen,_=subset(docs,[],order,n)
                path,_=materialize(folder,chosen,d,mode,block_cap,penalty)
                sizes[n]=path.stat().st_size;path.unlink()
            return sizes[n]
        for cap in CAPS:
            n,size=fit_prefix(len(docs),cap,probe)
            chosen,scoped=subset(docs,cases,order,n)
            path,stats=materialize(folder,chosen,d,mode,block_cap,penalty)
            assert path.stat().st_size==size<=cap
            result=evaluate(path,chosen,scoped,mode=="compact_individual")
            row=dict(mode=mode,storage_cap=cap,sqlite_bytes=size,docs_retained=n,
                complete_corpus=n==len(docs),probe_count=len(sizes),
                probe_sizes=dict(sorted(sizes.items())),elapsed_seconds=time.perf_counter()-start,
                build=stats,**result)
            results.append(row);path.unlink()
            print("ARM_JSON="+json.dumps(row),flush=True)
    # Paired counts against strongest compact independent schema.
    for row in results:
        ref=next(r for r in results if r["mode"]=="compact_individual" and r["storage_cap"]==row["storage_cap"])
        for a,b in zip(row["rows"],ref["rows"]):
            assert (a["context_budget"],a["decode_budget"])==(b["context_budget"],b["decode_budget"])
            a["wins_vs_compact"]=sum(x>y for x,y in zip(a["eligible_hit_bits"],b["eligible_hit_bits"]))
            a["losses_vs_compact"]=sum(x<y for x,y in zip(a["eligible_hit_bits"],b["eligible_hit_bits"]))
    return results

def main():
    p=argparse.ArgumentParser();p.add_argument("--out",type=Path,required=True)
    p.add_argument("--seed",type=int,required=True);p.add_argument("--policy",choices=("balanced","global"),required=True);a=p.parse_args()
    src=fetch_qasper();assert src["train"]["sha256"]==TRAIN_SHA and src["dev"]["sha256"]==DEV_SHA
    train=src["train"]["data"];dev=src["dev"]["data"];assert not set(train)&set(dev)
    docs,cases,cohort=load_dev(dev);assert len(docs)==13266 and len(cases)==1005
    samples,training=independently_trained_samples(train);d=train_dictionaries(samples,(65536,))[65536]
    with tempfile.TemporaryDirectory() as tmp:results=run(docs,cases,d,a.seed,a.policy,Path(tmp))
    out=dict(round=196,seed=a.seed,policy=a.policy,train_sha256=TRAIN_SHA,dev_sha256=DEV_SHA,
        dictionary_sha256=d["sha256"].hex(),training=training,cohort=cohort,layouts=results,
        limitations=["known-paper reused QASPER dev; no generated QA or tokenized context budgets",
        "labels and question text excluded from admission and layout; rank-based retrieval uses questions only after build",
        "fixed prefix admission, heuristic search over nonmonotonic SQLite file sizes, not optimal subset selection",
        "repartition adjacent retained paragraphs (may have gaps in original order); original source IDs and bytes preserved",
        "all dropped gold IDs retained in denominators as unavailable; union of mapped annotations, not sufficient alternative sets",
        "compact R102 schema has different metadata overhead from matched R195 block schema; both fully charged",
        "dictionary loaded once, raw decode bytes and activated frame payload not actual IO; no RSS, latency or updates",
        "complete corpus can fit some 8MiB arms; nonbinding explicitly reported; no claim of future generalization"])
    a.out.write_text(json.dumps(out,indent=2)+"\n");print("RESULT_JSON="+json.dumps(out),flush=True)
if __name__=="__main__":main()
