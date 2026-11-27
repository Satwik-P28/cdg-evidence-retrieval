"""R173: block-addressable positional postings over a versioned source archive.

R172 stored one delta-varint position list per term and decoded the whole list
on every query.  This round stores fixed blocks of B postings, each independently
addressable through a compact per-term directory of document-id ranges and
byte ranges, so a query decodes only blocks that can contain a candidate from
the frequency index.  Every block carries three separately addressable streams
(document-id deltas, per-document counts, position deltas) so a unigram lookup
reads only the first two.

Representations compared here:
  * ``dv``   delta varint (unsigned LEB128) per stream,
  * ``vw``   byte-aligned variable width (per-block frame of reference),
  * ``bp``   bit-packed (per-block bit width, no padding),
  * ``best`` per-stream minimum of the three with a two-bit tag,
  * raw or per-block Zstandard frames.

A ``unified`` archive stores no separate frequency postings: the block
document-id/count streams answer exact document frequency and term frequency,
while phrases decode the position stream of candidate blocks only.

All measurements are logical byte activation, not physical I/O.  Exact
overlapping phrase counts and historical BM25 are preserved by construction:
the intersection kernel is the R172 shifted-position kernel, and every ranked
result is compared with an independent native FTS5 oracle.
"""
import argparse,bisect,collections,ctypes,itertools,json,os,random,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-165"))
import signed_phrase as sp
import token_tape as tt
from frequency_index import f,h,si,connect,nr,ar,tokens,query_plan,prepare,recover
from compact_fragments import unpack
from forward_index import D,phrase_count

CODECS=("dv","vw","bp","best")
MAX_BLOCK_DECODE=1<<26

def load_kernel():
    """Optional native stream decoder; the Python decoders stay authoritative."""
    chosen=os.environ.get("CDG_BLOCK_KERNEL")
    if chosen in ("off","0"):return None
    path=Path(chosen) if chosen else HERE/"cdgbp.so"
    if not path.exists():return None
    try:lib=ctypes.CDLL(str(path))
    except OSError:return None
    fn=lib.cdg_decode_stream
    fn.restype=ctypes.c_int
    fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_size_t,ctypes.c_uint32,
                 ctypes.POINTER(ctypes.c_uint32)]
    return fn

KERNEL=load_kernel()

# ---------------------------------------------------------------- value streams

def _read_varint(raw,i):
    n=shift=0
    while True:
        if i>=len(raw):raise ValueError("truncated varint")
        b=raw[i];i+=1;n|=(b&127)<<shift
        if b<128:return n,i
        shift+=7
        if shift>63:raise ValueError("varint overflow")

def enc_dv(vals):
    out=bytearray();acc=0
    for v in vals:
        if v<0:raise ValueError("negative value")
        while v>=128:out.append((v&127)|128);v>>=7
        out.append(v);acc+=1
    return bytes(out)

def dec_dv(raw,count):
    out=[];i=0
    for _ in range(count):
        v,i=_read_varint(raw,i);out.append(v)
    if i!=len(raw):raise ValueError("trailing varint bytes")
    return out

def enc_vw(vals):
    w=1
    for v in vals:
        if v<0:raise ValueError("negative value")
        w=max(w,(v.bit_length()+7)//8)
    if w>4:raise ValueError("value width exceeds four bytes")
    out=bytearray([w]);ext=out.extend
    for v in vals:ext(v.to_bytes(w,"little"))
    return bytes(out)

def dec_vw(raw,count):
    if not raw:raise ValueError("empty width stream")
    w=raw[0]
    if not 1<=w<=4:raise ValueError("bad width")
    if len(raw)!=1+w*count:raise ValueError("width stream length")
    return [int.from_bytes(raw[1+i*w:1+(i+1)*w],"little") for i in range(count)]

def enc_bp(vals):
    w=max((v.bit_length() for v in vals),default=0)
    if w>32:raise ValueError("bit width exceeds 32")
    out=bytearray([w]);acc=bits=0
    for v in vals:
        acc|=v<<bits;bits+=w
        while bits>=8:out.append(acc&255);acc>>=8;bits-=8
    if bits:out.append(acc&255)
    return bytes(out)

def dec_bp(raw,count):
    if not raw:raise ValueError("empty bit-packed stream")
    w=raw[0]
    if w>32:raise ValueError("bad bit width")
    if len(raw)!=1+(w*count+7)//8:raise ValueError("bit-packed stream length")
    if w==0:return [0]*count
    out=[];acc=bits=0;i=1;mask=(1<<w)-1
    for _ in range(count):
        while bits<w:
            acc|=raw[i]<<bits;i+=1;bits+=8
        out.append(acc&mask);acc>>=w;bits-=w
    return out

def enc_stream(vals,codec):
    if codec=="dv":return 0,enc_dv(vals)
    if codec=="vw":return 1,enc_vw(vals)
    if codec=="bp":return 2,enc_bp(vals)
    if codec=="best":
        cands=[(len(b),tag,b) for tag,b in ((0,enc_dv(vals)),(1,enc_vw(vals)),(2,enc_bp(vals)))]
        _,tag,b=min(cands,key=lambda x:(x[0],x[1]))
        return tag,b
    raise ValueError("unknown codec "+repr(codec))

def dec_stream(tag,raw,count):
    if KERNEL is not None:
        if tag not in (0,1,2):raise ValueError("unknown codec tag "+repr(tag))
        buf=(ctypes.c_uint32*count)()
        if KERNEL(tag,raw,len(raw),count,buf)!=0:
            raise ValueError("native stream decode rejected tag %r"%(tag,))
        return buf
    if tag==0:return dec_dv(raw,count)
    if tag==1:return dec_vw(raw,count)
    if tag==2:return dec_bp(raw,count)
    raise ValueError("unknown codec tag "+repr(tag))

# ---------------------------------------------------------------- blocks

def encode_block(docs,codec,compress):
    """docs: [(cid,[positions])] strictly increasing. Returns stored block bytes."""
    if not docs:raise ValueError("empty block")
    first=docs[0][0]
    if first<0:raise ValueError("negative content id")
    cidv=[];prev=first;counts=[];posv=[]
    for n_doc,(cid,ps) in enumerate(docs):
        if not ps or (n_doc and cid<=prev):raise ValueError("posting order")
        cidv.append(cid-prev);prev=cid;counts.append(len(ps))
        last=-1
        for p in ps:
            if p<=last:raise ValueError("position order")
            posv.append(p-last);last=p
    streams=[enc_stream(cidv,codec),enc_stream(counts,codec),enc_stream(posv,codec)]
    out=bytearray()
    out+=encode_uint(len(docs))
    for tag,body in streams:
        out.append(tag);out+=encode_uint(len(body))
    for _,body in streams:out+=body
    raw=bytes(out)
    if compress:
        z=h.C.compress(raw)
        if len(z)<len(raw):return b"\x01"+bytes(z)
    return b"\x00"+raw

def encode_uint(v):
    out=bytearray()
    while v>=128:out.append((v&127)|128);v>>=7
    out.append(v);return bytes(out)

def parse_block(stored,first,with_positions):
    """Return parsed block plus (stored bytes activated, decoded bytes parsed)."""
    if not stored:raise ValueError("empty stored block")
    flag=stored[0]
    if flag==0:body=stored[1:]
    elif flag==1:body=D.decompress(stored[1:],max_output_size=MAX_BLOCK_DECODE)
    else:raise ValueError("unknown block encoding flag")
    n,i=_read_varint(body,0)
    if not n:raise ValueError("empty block header")
    heads=[]
    for _ in range(3):
        if i>=len(body):raise ValueError("truncated block header")
        tag=body[i];i+=1
        ln,i=_read_varint(body,i);heads.append((tag,ln))
    p=i;bodies=[]
    for tag,ln in heads:
        if p+ln>len(body):raise ValueError("block stream overflow")
        bodies.append(body[p:p+ln]);p+=ln
    if p!=len(body):raise ValueError("block length mismatch")
    cids=dec_stream(heads[0][0],bodies[0],n)
    counts=dec_stream(heads[1][0],bodies[1],n)
    absolute=list(itertools.accumulate(cids,initial=first))[1:]
    decoded=i+heads[0][1]+heads[1][1]
    positions=None
    if with_positions:
        values=dec_stream(heads[2][0],bodies[2],sum(counts))
        positions={};q=0
        for cid,cnt in zip(absolute,counts):
            positions[cid]=list(itertools.accumulate(values[q:q+cnt],initial=-1))[1:]
            q+=cnt
        decoded=i+sum(ln for _,ln in heads)
    return dict(cids=absolute,counts=counts,positions=positions,
                activated=len(stored),decoded=decoded)

def _deltas(vals):
    out=[];prev=0
    for v in vals:
        if v<prev:raise ValueError("nonincreasing directory")
        out.append(v-prev);prev=v
    return out

def encode_dir(firsts,offs,lens):
    out=bytearray();out+=encode_uint(len(firsts))
    for vals in (_deltas(firsts),_deltas(offs),lens):
        tag,body=enc_stream(vals,"best")
        out.append(tag);out+=encode_uint(len(body));out+=body
    return bytes(out)

def decode_dir(blob):
    n,i=_read_varint(blob,0);lists=[]
    for _ in range(3):
        if i>=len(blob):raise ValueError("truncated directory")
        tag=blob[i];i+=1
        ln,i=_read_varint(blob,i)
        lists.append(dec_stream(tag,blob[i:i+ln],n));i+=ln
    if i!=len(blob):raise ValueError("directory length mismatch")
    out=[]
    for k,vals in enumerate(lists):
        if k==2:out.append(list(vals));continue
        acc=[];cur=0
        for d in vals:
            cur+=d;acc.append(cur)
        out.append(acc)
    return out[0],out[1],out[2]

def encode_term(postings,block_size,codec,compress):
    """Encode one term's position postings into blocks plus a compact directory."""
    if block_size<1:raise ValueError("bad block size")
    body=bytearray();firsts=[];offs=[];lens=[]
    for start in range(0,len(postings),block_size):
        chunk=postings[start:start+block_size]
        stored=encode_block(chunk,codec,compress)
        firsts.append(chunk[0][0]);offs.append(len(body));lens.append(len(stored))
        body+=stored
    return dict(first_cids=firsts,offsets=offs,lengths=lens,
                dir=encode_dir(firsts,offs,lens),body=bytes(body),
                blocks=len(firsts),postings=len(postings))

def build_blocks(db,block_size,codec,compress,limit=None,lexicon=False):
    """Materialize block-addressable positions for all (or top-document-frequency) terms."""
    start=time.perf_counter_ns()
    if lexicon:db.execute("CREATE TABLE lexicon(tid INTEGER PRIMARY KEY,term TEXT NOT NULL)")
    db.execute("""CREATE TABLE term_blocks(tid INTEGER PRIMARY KEY,n_postings INTEGER NOT NULL,
        nblocks INTEGER NOT NULL,dir BLOB NOT NULL,body BLOB NOT NULL)""")
    db.execute("CREATE VIRTUAL TABLE temp.block_vocab USING fts5vocab(main,docs_0,'instance')")
    rows=db.execute("SELECT term,doc,offset FROM temp.block_vocab ORDER BY term,doc,offset")
    chosen=None
    if limit is not None:
        db.execute("CREATE VIRTUAL TABLE temp.block_rows USING fts5vocab(main,docs_0,'row')")
        chosen={t for t,_ in db.execute("SELECT term,doc FROM temp.block_rows ORDER BY doc DESC,term").fetchall()[:limit]}
        db.execute("DROP TABLE temp.block_rows")
    ids={};stats=collections.Counter()
    for term,group in itertools.groupby(rows,key=lambda r:r[0]):
        if chosen is not None and term not in chosen:continue
        postings=[(cid,[p for _,_,p in rs]) for cid,rs in itertools.groupby(group,key=lambda r:r[1])]
        enc=encode_term(postings,block_size,codec,compress)
        tid=len(ids)+1;ids[term.encode("utf8")]=tid
        if lexicon:db.execute("INSERT INTO lexicon VALUES(?,?)",(tid,term))
        db.execute("INSERT INTO term_blocks VALUES(?,?,?,?,?)",(tid,len(postings),enc["blocks"],enc["dir"],enc["body"]))
        stats["position_blocks"]+=enc["blocks"]
        stats["position_postings"]+=len(postings)
        stats["position_occurrences"]+=sum(len(p) for _,p in postings)
        stats["position_payload_bytes"]+=len(enc["body"])
        stats["position_directory_bytes"]+=len(enc["dir"])
    db.execute("DROP TABLE temp.block_vocab")
    return dict(selected_terms=len(ids),block_size=block_size,codec=codec,
                compression="zstd" if compress else "raw",
                block_build_us=(time.perf_counter_ns()-start)/1000,**stats)

# ---------------------------------------------------------------- query time

def shifted_count(covered,dl,length):
    """Exact overlapping phrase TF for full coverage; upper bound otherwise."""
    if not covered:raise ValueError("empty coverage")
    i,positions=min(covered,key=lambda x:len(x[1]))
    starts={p-i for p in positions if 0<=p-i<=dl-length}
    for j,ps in covered:
        if j!=i:starts.intersection_update(p-j for p in ps)
        if not starts:break
    return len(starts)

class BlockIndex:
    """Per-query view: decodes only blocks that contain a candidate document."""

    def __init__(self,db,ids,has_frequency):
        self.db=db;self.ids=ids;self.has_frequency=has_frequency
        self.dirs={};self.blocks={};self.counts={};self.work=collections.Counter()

    def reset(self):
        """Drop per-query caches; term directories stay resident."""
        self.blocks.clear();self.counts.clear();self.work.clear()

    def directory(self,tid):
        if tid in self.dirs:return self.dirs[tid]
        row=self.db.execute("SELECT n_postings,nblocks,dir,body FROM term_blocks WHERE tid=?",(tid,)).fetchone()
        if row is None:d=None
        else:
            npost,nblocks,blob,body=row
            firsts,offs,lens=decode_dir(blob)
            if not (len(firsts)==len(offs)==len(lens)==nblocks):raise ValueError("directory shape")
            d=dict(n=npost,firsts=firsts,offs=offs,lens=lens,body=body)
            self.work["directory_bytes_activated"]+=len(blob)
        self.dirs[tid]=d
        return d

    def block_of(self,tid,cid):
        d=self.directory(tid)
        k=bisect.bisect_right(d["firsts"],cid)-1
        return None if k<0 else k

    def block(self,tid,k,positions=False):
        key=(tid,k);b=self.blocks.get(key)
        if b is not None and (not positions or b["positions"] is not None):return b
        d=self.directory(tid)
        if not 0<=k<len(d["offs"]):raise ValueError("block index out of range")
        off,ln,first=d["offs"][k],d["lens"][k],d["firsts"][k]
        stored=d["body"][off:off+ln]
        if len(stored)!=ln:raise ValueError("truncated block payload")
        fresh=b is None
        b=parse_block(stored,first,positions)
        if fresh:
            self.work["blocks_activated"]+=1
            self.work["storage_bytes_activated"]+=b["activated"]
        else:self.work["blocks_upgraded"]+=1
        self.work["decoded_bytes"]+=b["decoded"]
        self.blocks[key]=b
        return b

    def group_blocks(self,tid,cids):
        groups=collections.defaultdict(list)
        for cid in sorted(cids):
            k=self.block_of(tid,cid)
            if k is None:continue
            groups[k].append(cid)
        self.work["block_batches"]+=len(groups)
        return groups

    def all_counts(self,tid):
        """Exact document frequency and term frequency for one term (cached per query)."""
        cached=self.counts.get(tid)
        if cached is not None:return cached
        out=None
        if self.has_frequency:
            row=self.db.execute("SELECT n,z,body FROM token_postings WHERE tid=?",(tid,)).fetchone()
            if row is not None:
                self.work["posting_bytes"]+=len(row[2])
                out=dict(unpack(tt.unpayload(*row)))
        if out is None:
            if self.directory(tid) is None:out={}
            else:
                out={}
                for k in range(len(self.directory(tid)["firsts"])):
                    b=self.block(tid,k)
                    out.update(zip(b["cids"],b["counts"]))
        self.counts[tid]=out
        return out

def rank_blocked(db,p,o,prep,index):
    """Exact historical BM25 with block-addressable positions."""
    ar.expression(p,o);active,lens,n,total=prep;freq=[]
    index.reset()
    for phrase in p:
        qs=tokens(db,phrase)
        qids=[index.ids.get(t) for t in qs]
        if None in qids:freq.append({});continue
        if len(qids)==1:
            matches={cid:tf for cid,tf in index.all_counts(qids[0]).items() if cid in active}
        else:
            distinct=list(dict.fromkeys(qids))
            dirs={t:index.directory(t) for t in distinct}
            if index.has_frequency:
                maps={t:index.all_counts(t) for t in distinct}
                candidates={cid for cid in set.intersection(*(set(maps[t]) for t in distinct)) if cid in active}
            else:
                if any(v is None for v in dirs.values()):freq.append({});continue
                base=min(distinct,key=lambda t:dirs[t]["n"])
                candidates={cid for cid in index.all_counts(base) if cid in active}
                for t in distinct:
                    if t==base or not candidates:continue
                    keep=set()
                    for k,cids in index.group_blocks(t,candidates).items():
                        present=set(index.block(t,k)["cids"])
                        keep.update(c for c in cids if c in present)
                    candidates=keep
            index.work["candidate_checks"]+=len(candidates)
            covered=[(i,t) for i,t in enumerate(qids) if dirs[t] is not None]
            complete=len(covered)==len(qids)
            matches={};cache={}
            for cid in candidates:
                lists=None;upper=None
                if len(covered)>=2:
                    lists=[]
                    for i,t in covered:
                        k=index.block_of(t,cid)
                        if k is None:lists=None;break
                        ps=index.block(t,k,True)["positions"].get(cid)
                        if ps is None:lists=None;break
                        lists.append((i,ps))
                    if lists is not None:
                        upper=shifted_count(lists,lens[active[cid][0]],len(qids))
                        if not upper:
                            index.work["position_rejections"]+=1;continue
                        if complete:
                            matches[cid]=upper;index.work["position_exact"]+=1;continue
                if cid not in cache:
                    raw,dd,ab=recover(db,cid)
                    cache[cid]=b" ".join(tokens(db,raw.decode("utf8")))
                    index.work["source_reads"]+=1
                    index.work["source_decoded_bytes"]+=dd
                    index.work["source_activated_bytes"]+=ab
                tf=phrase_count(cache[cid],qs)
                if upper is not None and tf>upper:raise AssertionError("position bound violated")
                if tf:matches[cid]=tf
                index.work["source_resolved"]+=1
        expanded={g:tf for cid,tf in matches.items() for g in active[cid]}
        if any(not 1<=tf<=lens[g] for g,tf in expanded.items()):raise ValueError("frequency bound")
        freq.append(expanded)
    hits,df=ar.score(freq,o,n,total,lens)
    return hits,df,index.work

# ---------------------------------------------------------------- storage sweep

SWEEP_CONFIGS=tuple(
    [(b,c,z) for b in (32,64,128,256,512) for c in ("dv","best") for z in (False,True)]
    +[(128,c,z) for c in ("vw","bp") for z in (False,True)])

def sweep_key(block,codec,compress):
    return "b%d-%s-%s"%(block,codec,"zstd" if compress else "raw")

def storage_sweep(db):
    """Exact per-configuration position payload and directory bytes."""
    totals={sweep_key(*c):collections.Counter() for c in SWEEP_CONFIGS}
    db.execute("CREATE VIRTUAL TABLE temp.sweep_vocab USING fts5vocab(main,docs_0,'instance')")
    terms=occurrences=pairs=0
    for term,group in itertools.groupby(db.execute("SELECT term,doc,offset FROM temp.sweep_vocab ORDER BY term,doc,offset"),key=lambda r:r[0]):
        postings=[(cid,[p for _,_,p in rs]) for cid,rs in itertools.groupby(group,key=lambda r:r[1])]
        terms+=1;pairs+=len(postings);occurrences+=sum(len(p) for _,p in postings)
        for block,codec,compress in SWEEP_CONFIGS:
            enc=encode_term(postings,block,codec,compress)
            t=totals[sweep_key(block,codec,compress)]
            t["payload_bytes"]+=len(enc["body"]);t["directory_bytes"]+=len(enc["dir"])
            t["blocks"]+=enc["blocks"]
    db.execute("DROP TABLE temp.sweep_vocab")
    out={}
    for key,t in totals.items():
        block,codec,compress=next(c for c in SWEEP_CONFIGS if sweep_key(*c)==key)
        out[key]=dict(block_size=block,codec=codec,compression="zstd" if compress else "raw",
            terms=terms,postings=pairs,occurrences=occurrences,blocks=t["blocks"],
            payload_bytes=t["payload_bytes"],directory_bytes=t["directory_bytes"],
            total_bytes=t["payload_bytes"]+t["directory_bytes"]+24*terms,
            bytes_per_occurrence=(t["payload_bytes"]+t["directory_bytes"])/max(1,occurrences))
    return out

def quant_us(xs):
    if not xs:return dict(median_us=0.0,p95_us=0.0,p99_us=0.0,max_us=0.0,samples=0)
    s=sorted(xs)
    return dict(median_us=s[len(s)//2],p95_us=s[int(.95*(len(s)-1))],p99_us=s[int(.99*(len(s)-1))],
                max_us=s[-1],samples=len(s))

# ---------------------------------------------------------------- arms

def arm_specs():
    return [
        ("positional",dict(kind="native")),
        ("adaptive",dict(kind="adaptive")),
        ("frequency",dict(kind="frequency")),
        ("r172_top32",dict(kind="r172",limit=32)),
        ("r172_all",dict(kind="r172",limit=None)),
        ("duplex_b32_best_zstd",dict(kind="blocked",block=32,codec="best",compress=True,unified=False)),
        ("duplex_b128_best_zstd",dict(kind="blocked",block=128,codec="best",compress=True,unified=False)),
        ("duplex_b512_best_zstd",dict(kind="blocked",block=512,codec="best",compress=True,unified=False)),
        ("unified_b16_best_zstd",dict(kind="blocked",block=16,codec="best",compress=True,unified=True)),
        ("unified_b32_best_zstd",dict(kind="blocked",block=32,codec="best",compress=True,unified=True)),
        ("unified_b64_best_zstd",dict(kind="blocked",block=64,codec="best",compress=True,unified=True)),
        ("unified_b128_best_zstd",dict(kind="blocked",block=128,codec="best",compress=True,unified=True)),
        ("unified_b512_best_zstd",dict(kind="blocked",block=512,codec="best",compress=True,unified=True)),
        ("unified_b128_dv_raw",dict(kind="blocked",block=128,codec="dv",compress=False,unified=True)),
        ("unified_b128_bp_raw",dict(kind="blocked",block=128,codec="bp",compress=False,unified=True)),
    ]

def build_arm(path,ext,events,spec):
    import selective_positions as sp172
    db,size=f.build(path,ext,events,"marginal",False)
    if spec["kind"]=="r172":
        size.update(sp172.build_positions(db,spec["limit"]))
        size.update(tt.build_tape(db,path,events,"frequency"))
        size["index_bytes"]=size.get("index_bytes",0)+size["table_bytes"].get("term_positions",0)
    elif spec["kind"]=="adaptive":
        size.update(sp.build_delta(db,path,events,"independent_adaptive_weighted_adjusted_multi"))
    elif spec["kind"]=="frequency":
        size.update(tt.build_tape(db,path,events,"frequency"))
    elif spec["kind"]=="blocked":
        lexicon=spec["unified"]
        meta=build_blocks(db,spec["block"],spec["codec"],spec["compress"],lexicon=lexicon)
        if not lexicon:
            block_ids=set(range(1,meta["selected_terms"]+1))
            size.update(tt.build_tape(db,path,events,"frequency"))
            tape_ids={tid for tid, in db.execute("SELECT tid FROM lexicon")}
            if block_ids!=tape_ids:raise AssertionError("block and tape vocabulary differ")
        else:
            # The block index is the only term index in a unified archive.
            db.execute("DROP TABLE IF EXISTS docs_0")
        size.update(meta)
        db.commit();db.execute("VACUUM")
    db.close()
    return size

def run(events,manifest,cuts,folder,ext,corpus,only=None,sweep=False):
    refs={c:h.active_oracle(events,c) for c in cuts}
    qs=query_plan(events,cuts[0],refs[cuts[0]])
    expected={(c,p,o):h.native(ref,p,o) for c,ref in refs.items() for p,o in qs}
    results={};sigs={}
    import selective_positions as sp172
    for name,spec in arm_specs():
        if only and name not in only:continue
        path=folder/(name+".sqlite")
        size=build_arm(path,ext,events,spec)
        db=connect(path,ext);ids={};index=None
        t=time.perf_counter_ns()
        if spec["kind"]=="adaptive":mapping=sp.load_patch_map(db)
        elif spec["kind"] in ("frequency","r172","blocked"):
            ids,_=tt.vocabulary(db)
            if spec["kind"]=="blocked":index=BlockIndex(db,ids,not spec["unified"])
            elif spec["kind"]=="r172":selected={tid for tid, in db.execute("SELECT tid FROM term_positions")}
        setup=(time.perf_counter_ns()-t)/1000
        for g,(_,_,want) in enumerate(events,1):
            raw,dd,ab=recover(db,g)
            if raw!=want:raise AssertionError("source reconstruction mismatch")
        preps={};pt=[]
        for c in cuts:
            t=time.perf_counter_ns()
            preps[c]=sp.prepare_delta(db,c,mapping) if spec["kind"]=="adaptive" else prepare(db,c)
            pt.append((time.perf_counter_ns()-t)/1000)
        plan=list(expected);rng=random.Random(173);times=[];classes=collections.defaultdict(list)
        work=collections.Counter();err=0.
        for _ in range(2):
            rng.shuffle(plan)
            for c,p,o in plan:
                group="unigram_only" if all(len(tokens(db,q))==1 for q in p) else "has_phrase"
                t=time.perf_counter_ns()
                if spec["kind"]=="native":hits,df=si.rank(db,1,p,o,preps[c])
                elif spec["kind"]=="adaptive":hits,df,w=sp.rank_delta(db,p,o,preps[c]);work.update(w)
                elif spec["kind"]=="frequency":hits,df,w=tt.rank_tape(db,p,o,preps[c],"frequency",ids);work.update(w)
                elif spec["kind"]=="r172":hits,df,w=sp172.rank_selective(db,p,o,preps[c],ids,selected);work.update(w)
                else:hits,df,w=rank_blocked(db,p,o,preps[c],index);work.update(w)
                dt=(time.perf_counter_ns()-t)/1000;times.append(dt);classes[group].append(dt)
                err=max(err,h.verify(hits,expected[c,p,o]))
                if (c,p,o) in sigs:
                    if sigs[c,p,o][0]!=hits:raise AssertionError("repeat mismatch")
                else:sigs[c,p,o]=(hits,df)
        sizes=dict(db.execute("SELECT name,sum(pgsize) FROM dbstat GROUP BY name"))
        size["table_bytes"]=sizes
        size["fts_bytes"]=sum(v for k,v in sizes.items() if k.startswith("docs_"))
        size["index_bytes"]=sum(v for k,v in sizes.items() if k in
            ("lexicon","token_postings","term_blocks","term_positions","base_fts_data","patch_fts_data","base_fts_idx","patch_fts_idx"))
        size["sqlite_bytes"]=path.stat().st_size
        results[name]=dict(**size,setup_us=setup,prepare=quant_us(pt),source_checks=len(events),
            query=quant_us(times),query_by_class={k:quant_us(v) for k,v in classes.items()},
            rank_checks=len(times),score_error=err,work=dict(work))
        print("ARM_JSON="+json.dumps(results[name]),flush=True);db.close()
    for ref in refs.values():ref.close()
    return dict(round=173,corpus=corpus,revisions=len(events),manifest_sha256=manifest,
        cutoffs=cuts,query_count=len(qs),query_plan_sha256=h.sha(h.canonical(qs)).hex(),policies=results,
        sweep_blocksize_codec_compression=SWEEP_CONFIGS,
        limitations=[
          "finalized matched archive; no transaction or crash guarantee",
          "all byte figures are logical activation of stored block/directory bytes, not physical page I/O",
          "positions cover every term in blocked arms; r172_top32 is the selective control",
          "directory row proxy 24 bytes per term in the storage sweep; end-to-end arms charge real dbstat pages",
          "two shuffled warm passes over one frozen query plan; no cold-cache or held-out workload claim",
          "unified arms derive document frequency from block count streams, so no separate frequency postings exist",
          "Python decoder; a native kernel was profiled but is not part of these measurements"])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True)
    p.add_argument("--corpus",choices=("ap","clark"),required=True)
    p.add_argument("--target",type=int,default=10000);p.add_argument("--extension",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True);p.add_argument("--only",default="")
    p.add_argument("--sweep",action="store_true");a=p.parse_args()
    only={x for x in a.only.split(",") if x} or None
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        if a.corpus=="clark":
            import clark_retrieval as cr
            events,_,m,_,_=cr.read(a.source);manifest=h.sha(h.canonical(m)).hex()
            if manifest!="1567b6c765b7a648e1a2a6d4221bf22543a7011377fda94161c37c04a29b6e2f":raise ValueError("CLARK manifest")
            n=len(events);cuts=[n//4,n//2,3*n//4,n]
        else:
            events,_,m=nr.load(a.source,a.target,folder);manifest=m["source_manifest_sha256"]
            n=len(events);first=len(m["retained_paths"]);cuts=[first,first+(n-first)//3,first+2*(n-first)//3,n]
            got=json.loads((HERE.parent/"round-152"/("results-ap-"+str(n)+".json")).read_text())["manifest_sha256"]
            if manifest!=got:raise ValueError("AP manifest")
        result=run(events,manifest,cuts,folder,a.extension.resolve(),a.corpus,only,a.sweep)
        if a.sweep:
            db,_=f.build(folder/"sweep.sqlite",a.extension.resolve(),events,"marginal",False)
            result["storage_sweep"]=storage_sweep(db);db.close()
        if a.out.exists():
            try:old=json.loads(a.out.read_text())
            except ValueError:old=None
            if old and old.get("manifest_sha256")==manifest:
                old["policies"].update(result["policies"])
                if "storage_sweep" in result:old["storage_sweep"]=result["storage_sweep"]
                result=old
    a.out.write_text(json.dumps(result,indent=2)+"\n");print("RESULT_JSON="+json.dumps(result),flush=True)
