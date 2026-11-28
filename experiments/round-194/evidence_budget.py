"""R194: identical QASPER top-ten candidates, two strict byte budgets."""
import argparse,collections,json,random,statistics,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-103"))
from joint_group_dictionary import (fetch_qasper,load_dev,gold_recall,document_bytes,
    base_fts_db,make_grouped_brotli,queries_for_original,group_variant,
    GroupSourceReader,verify_all_originals,independently_trained_samples,
    train_dictionaries,TRAIN_SHA,DEV_SHA)
from selector import choose,totals
BUDGETS=((2048,4096),(4096,8192),(4096,32768))
POLICIES=("rank","context","shared","exact")
LAYOUTS=((1,"brotli5"),(1,"zstd9-dictionary"),(4,"zstd9-dictionary"),
         (8,"zstd9-dictionary"),("paper","zstd9-dictionary"))

def quant(xs):
    xs=sorted(xs)
    return dict(median_us=statistics.median(xs),p95_us=xs[int(.95*(len(xs)-1))])

def paired(cases,base,new):
    # Cluster by paper, retain entire eligible-question cluster. Descriptive
    # bootstrap on the reused dev benchmark, not new independent test data.
    groups=collections.defaultdict(list)
    for c in cases:
        if c["gold_rowids"]:
            groups[c["paper"]].append(new[c["id"]]-base[c["id"]])
    stats=[(sum(v),len(v)) for v in groups.values()]
    rng=random.Random(194);boot=[]
    for _ in range(500):
        draw=rng.choices(stats,k=len(stats))
        boot.append(sum(x for x,_ in draw)/sum(n for _,n in draw))
    boot.sort()
    ds=[d for v in groups.values() for d in v]
    return dict(wins=sum(d>0 for d in ds),losses=sum(d<0 for d in ds),
        delta=sum(ds)/len(ds),paper_cluster_bootstrap_95=[boot[12],boot[487]])

def evaluate(db,docs,cases,ranked):
    t=time.perf_counter_ns()
    meta={r:(b,n) for r,b,n in db.execute("SELECT rowid,block_id,utf8_len FROM source_receipts")}
    blocks={b:(n,z) for b,n,z in db.execute("SELECT block_id,utf8_len,length(compressed) FROM source_blocks")}
    reader=GroupSourceReader(db)
    setup=(time.perf_counter_ns()-t)/1000
    assert len(meta)==len(docs)
    verified=verify_all_originals(reader,docs)
    output=[]
    for context,decode in BUDGETS:
        counters={p:collections.Counter() for p in POLICIES}
        timing={p:[] for p in POLICIES};reads={p:[] for p in POLICIES};bits={p:{} for p in POLICIES}
        for c in cases:
            rs=ranked[c["id"]];gold=c["gold_rowids"]
            weights={r:1000000//(i+1) for i,r in enumerate(rs)};utility={}
            # Alternate policy order deterministically to limit warm-order bias.
            order=list(POLICIES);random.Random(194+len(timing["rank"])).shuffle(order)
            for p in order:
                t=time.perf_counter_ns()
                ids=choose(rs,meta,blocks,context,decode,p)
                timing[p].append((time.perf_counter_ns()-t)/1000)
                cb,dbb,encoded=totals(ids,meta,blocks)
                assert cb<=context and dbb<=decode and len(ids)==len(set(ids))
                cache={};actual=0;t=time.perf_counter_ns()
                for rid in ids:
                    x=reader.read(rid,cache)
                    assert x["doc_id"]==str(docs[rid-1]["doc_id"])
                    assert x["source_bytes"]==document_bytes(docs[rid-1])
                    actual+=x["decoded_block_bytes"]
                reads[p].append((time.perf_counter_ns()-t)/1000)
                assert actual==dbb
                cnt=counters[p];cnt["questions"]+=1;cnt["context_bytes"]+=cb
                cnt["decoded_bytes"]+=dbb;cnt["activated_compressed_payload_bytes"]+=encoded
                cnt["selected_passages"]+=len(ids);cnt["source_checks"]+=len(ids)
                cnt["empty"]+=not ids
                utility[p]=sum(weights[r] for r in ids);cnt["rank_utility"]+=utility[p]
                if gold:
                    hits=len(set(ids)&gold)
                    cnt["eligible"]+=1;cnt["hit"]+=bool(hits)
                    cnt["gold_found"]+=hits;cnt["gold_total"]+=len(gold)
                    cnt["gold_union_complete"]+=hits==len(gold)
                    cnt["any_feasible_gold"]+=any(meta[r][1]<=context and blocks[meta[r][0]][0]<=decode for r in rs if r in gold)
                    bits[p][c["id"]]=int(bool(hits))
            assert utility["exact"]>=max(utility[p] for p in POLICIES)
        for p in POLICIES:
            cnt=dict(counters[p]);cnt["policy"]=p;cnt["context_budget"]=context;cnt["decode_budget"]=decode
            cnt["selection_us"]=quant(timing[p]);cnt["read_and_verify_us"]=quant(reads[p])
            cnt["paired_vs_rank"]=paired(cases,bits["rank"],bits[p])
            output.append(cnt)
    return dict(all_source_checks=verified,metadata_setup_us=setup,rows=output)

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--out",type=Path,required=True);a=parser.parse_args()
    src=fetch_qasper()
    assert src["train"]["sha256"]==TRAIN_SHA and src["dev"]["sha256"]==DEV_SHA
    train=src["train"]["data"];dev=src["dev"]["data"];assert not set(train)&set(dev)
    docs,cases,cohort=load_dev(dev);assert len(docs)==13266 and len(cases)==1005
    samples,training=independently_trained_samples(train)
    d=train_dictionaries(samples,(65536,))[65536]
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp);base=folder/"fts.sqlite";db=base_fts_db(base,docs)
        ranked=queries_for_original(docs,cases,db);db.close()
        rows=[]
        for group,codec in LAYOUTS:
            grouped=folder/"grouped.sqlite";db=make_grouped_brotli(grouped,base,docs,group);db.close()
            path=folder/"archive.sqlite";db,_=group_variant(path,grouped,codec,d)
            assert queries_for_original(docs,cases,db)==ranked
            result=evaluate(db,docs,cases,ranked);size=path.stat().st_size
            row=dict(group=group,codec=codec,sqlite_bytes=size,**result)
            rows.append(row);db.close();path.unlink();grouped.unlink()
            print("ARM_JSON="+json.dumps(row),flush=True)
    out=dict(round=194,train_sha256=TRAIN_SHA,dev_sha256=DEV_SHA,source_docs=len(docs),
        questions=len(cases),cohort=cohort,training=training,dict_sha256=d["sha256"].hex(),
        full_top10_gold=gold_recall(cases,ranked),layouts=rows,
        limitations=["known-paper QASPER dev reused; top ten fixed candidates; no answer generation",
        "UTF8 source bytes including title, not model tokenizer/context tokens; no prompt overhead",
        "decode budget logical raw block bytes; no physical I/O or wall-clock limit",
        "resident metadata setup separate; no peak RSS; no ranking time in selection/read timings",
        "exact solver maximizes fixed reciprocal-rank utility, not human gold; at most 10 candidates",
        "whole archive measured but not constrained to same persistent size across layouts",
        "union of mapped evidence annotations, not alternative sufficient evidence chains",
        "descriptive within-dev paired paper-cluster bootstrap, no prospective test claim"])
    a.out.write_text(json.dumps(out,indent=2)+"\n");print("RESULT_JSON="+json.dumps(out),flush=True)
if __name__=="__main__":main()
