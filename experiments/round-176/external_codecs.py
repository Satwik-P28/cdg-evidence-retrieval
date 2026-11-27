"""R176: established posting encoders measured on this archive's own postings.

Implements, from published specifications, the encodings used by the external
systems studied in this round, and applies all of them to the same logical data:

  * Elias-Fano (Vigna; PISA ``compact_elias_fano``) for sorted document ids,
  * SIMD-BP128 (Lemire & Boytsov 2015; PISA ``block_simdbp``, block size 128),
  * Roaring bitmaps (Chambi/Lemire; CRoaring ``DEFAULT_MAX_SIZE = 4096``),
  * delta varint (protobuf/PISA ``interpolative``-style baseline, our ``dv``),
  * our R173 block codec (``best`` + per-block Zstandard).

Pinned external revisions and licence files are recorded in
``research/rounds/round-176/external.md``.  No external source code is copied;
these are independent implementations of the published layouts, validated by the
size identities asserted in ``tests/test_external_codecs.py``.

Document-only encoders cannot represent positions, so they are compared on the
frequency index (document id + term frequency) only, and the positional payload is
compared separately against the R172 single-blob layout.
"""
import argparse,collections,json,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-173"))
from blocked_positions import encode_term,f,h,nr,tokens,recover

def tf_bytes(tfs):
    return sum(1 if tf<128 else 2 if tf<16384 else 3 for tf in tfs)

def delta_varint_size(docids):
    total=0;prev=0
    for cid in docids:
        d=cid-prev;prev=cid
        total+=1 if d<128 else 2 if d<16384 else 3 if d<2097152 else 4
    return total

def elias_fano_size(docids,universe):
    """Corpus-wide Elias-Fano over the concatenated posting lists of one term."""
    n=len(docids)
    if n==0:return 0
    if universe//n<=1:return n*2
    low=universe//n
    l=low.bit_length()-1
    high=[cid>>l for cid in docids]
    upper=sum(1 for _ in high)+max(high)+1 if high else 0
    return ((n*l)+7)//8+((upper)+7)//8

def simdbp128_size(docids):
    """SIMD-BP128 on document-id deltas: 1 header byte per 128 values."""
    if not docids:return 0
    deltas=[];prev=0
    for cid in docids:
        deltas.append(cid-prev);prev=cid
    total=0
    for start in range(0,len(deltas),128):
        block=deltas[start:start+128]
        width=max(block).bit_length() if block else 0
        total+=1+((len(block)*width+7)//8)
    return total

def roaring_size(docids):
    """Roaring: array containers up to 4096 values (2 B each), else 8 KiB bitmaps."""
    if not docids:return 0
    chunks=collections.Counter(cid>>16 for cid in docids)
    total=4
    for key,n in sorted(chunks.items()):
        total+=(4+8192) if n>4096 else (4+2*n)
    return total

def collect_postings(db):
    """term -> [(cid, [positions])] in cid order, straight from the source bytes."""
    post=collections.defaultdict(list)
    cids=[cid for cid, in db.execute("SELECT cid FROM contents ORDER BY cid")]
    for cid in cids:
        g=db.execute("SELECT min(g) FROM revisions WHERE cid=?",(cid,)).fetchone()[0]
        raw,_,_=recover(db,g)
        per=collections.defaultdict(list)
        for i,tok in enumerate(tokens(db,raw.decode("utf8"))):per[tok].append(i)
        for tok,ps in per.items():post[tok].append((cid,ps))
    return post,len(cids)

def measure(db):
    post,ncontents=collect_postings(db)
    universe=db.execute("SELECT max(cid) FROM contents").fetchone()[0]
    acc=collections.Counter();terms=0;pairs=0;occurrences=0
    for term in sorted(post):
        rows=post[term]
        docids=[cid for cid,_ in rows];tfs=[len(ps) for _,ps in rows]
        terms+=1;pairs+=len(docids);occurrences+=sum(tfs)
        acc["dv_docid"]+=delta_varint_size(docids)
        acc["ef_docid"]+=elias_fano_size(docids,universe)
        acc["simdbp_docid"]+=simdbp128_size(docids)
        acc["roaring_docid"]+=roaring_size(docids)
        acc["tf"]+=tf_bytes(tfs)
        enc=encode_term(rows,512,"best","zstd")
        acc["r173_blocks"]+=len(enc["body"])+len(enc["dir"])
        acc["r173_payload"]+=len(enc["body"])
        acc["r173_directory"]+=len(enc["dir"])
        gaps=[]
        for _,ps in rows:
            prev=0
            for p in ps:gaps.append(p-prev);prev=p
        # within-document position gaps, concatenated; document boundaries come from
        # the docid/term-frequency stream, so no directory is charged either way
        acc["position_gaps_simdbp"]+=simdbp128_size(gaps)
        acc["position_gaps_dv"]+=delta_varint_size(gaps)
    return dict(terms=terms,pairs=pairs,occurrences=occurrences,universe=universe,
                contents=ncontents,bytes=dict(acc),total=dict(acc))

def report(db):
    m=measure(db)
    b=m["bytes"]
    out={}
    out["frequency_document_id_plus_tf"]={
        "delta_varint":b["dv_docid"]+b["tf"],
        "elias_fano":b["ef_docid"]+b["tf"],
        "simd_bp128":b["simdbp_docid"]+b["tf"],
        "roaring":b["roaring_docid"]+b["tf"]}
    out["frequency_tf_only"]={"varint":b["tf"]}
    out["positional"]={"r173_blocks_b512_best_zstd":b["r173_blocks"],
                       "r173_payload_b512_best_zstd":b["r173_payload"],
                       "r173_directory":b["r173_directory"],
                       "r172_single_blob_dv_zstd_reference":8998912,
                       "external_flat_simdbp_docid_tf_positions":
                           b["simdbp_docid"]+b["tf"]+b["position_gaps_simdbp"],
                       "external_flat_delta_varint_docid_tf_positions":
                           b["dv_docid"]+b["tf"]+b["position_gaps_dv"]}
    out["logical"]={k:m[k] for k in ("terms","pairs","occurrences","universe")}
    out["note"]=("document-only encoders cannot store positions; the frequency table "
                 "charges 1-3 varint bytes for term frequency on top of the document ids")
    return out

def run(source,target,folder,ext,corpus):
    if corpus=="clark":
        import clark_retrieval as cr
        events,_,m,_,_=cr.read(source);manifest=h.sha(h.canonical(m)).hex()
        if manifest!="1567b6c765b7a648e1a2a6d4221bf22543a7011377fda94161c37c04a29b6e2f":raise ValueError("CLARK manifest")
        cuts=None
    else:
        events,_,m=nr.load(source,target,folder);manifest=m["source_manifest_sha256"]
        got=json.loads((HERE.parent/"round-152"/("results-ap-"+str(len(events))+".json")).read_text())["manifest_sha256"]
        if manifest!=got:raise ValueError("AP manifest")
        cuts=None
    del cuts
    db,_=f.build(folder/"ext.sqlite",ext,events,"marginal",False)
    out=report(db)
    db.close()
    return dict(round=176,corpus=corpus,revisions=len(events),manifest_sha256=manifest,
        **out,limitations=[
          "size-only comparison of published layouts, not a runtime benchmark of the external systems",
          "no external source code copied; layouts reimplemented from specifications and validated by unit tests",
          "document-only encoders are charged the same term-frequency bytes so the comparison is feature-matched",
          "PISA/CRoaring/folly/FastPFor were not built or executed in this environment"])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True)
    p.add_argument("--corpus",choices=("ap","clark"),required=True)
    p.add_argument("--target",type=int,default=10000);p.add_argument("--extension",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        result=run(a.source,a.target,Path(tmp),a.extension.resolve(),a.corpus)
    a.out.write_text(json.dumps(result,indent=2)+"\n");print("RESULT_JSON="+json.dumps(result),flush=True)
