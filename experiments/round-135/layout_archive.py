"""R135: finalized layout-matched source storage and published WikECD control."""
import argparse,collections,datetime,gzip,importlib.metadata,json,os,random,sqlite3,struct,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"round-134"))
from pack_archive import verify_archive
import heldout_archive as h
import versioned_evidence as ve
from anchor_bench import D,delta_decode
from WikECD.sources.base import Revision
from WikECD.compression.compressor import compress_article
from WikECD.storage.serializer import dumps,loads
from WikECD.retrieval.retrieval import retrieve_range

PTR=struct.Struct(">QQ")
def pointer(raw):
    if len(raw)!=PTR.size:raise ValueError("invalid pointer")
    return PTR.unpack(raw)

def fetch_frame(file,raw):
    off,n=pointer(raw);file.seek(off);data=file.read(n)
    if len(data)!=n:raise ValueError("truncated sidecar")
    return data

def finalize(db,path):
    db.commit();db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    db.execute("PRAGMA journal_mode=DELETE");db.execute("VACUUM")
    assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    return path.stat().st_size

class Frames:
    def __init__(self,file):self.file=file
    def recover(self,db,a,i,expected=None):
        row=db.execute("SELECT n,digest,depth,parent_ord,payload FROM versions WHERE article=? AND ord=?",(a,i)).fetchone()
        if row is None:raise ValueError("missing source")
        n,digest,depth,parent,ptr=row
        if expected is not None and depth!=expected:raise ValueError("depth")
        frame=fetch_frame(self.file,ptr)
        if depth==0:
            if parent is not None:raise ValueError("literal parent")
            raw=D.decompress(frame,max_output_size=n+1);ab=len(frame);dd=len(raw)
        else:
            if not 0<=parent<i or depth!=1:raise ValueError("invalid anchor")
            base,ab,dd,_=self.recover(db,a,parent,0)
            raw=delta_decode(frame,base,n);ab+=len(frame);dd+=len(raw)
        if len(raw)!=n or h.sha(raw)!=digest:raise ValueError("source digest")
        return raw,ab,dd,depth

def export_frames(db,file):
    rows=db.execute("SELECT article,ord,payload FROM versions ORDER BY article,ord").fetchall()
    for a,i,p in rows:
        off=file.tell();file.write(p)
        db.execute("UPDATE versions SET payload=? WHERE article=? AND ord=?",(PTR.pack(off,len(p)),a,i))
    return sum(len(p) for _,_,p in rows)

def create_wiki(title,revisions,budget):
    art=compress_article(title,revisions,time_budget=budget)
    bases={i:revisions[i].text for i in art.anchors}
    return dumps(art,bases)

class WikiReader:
    def __init__(self,file):
        self.file=file;self.serialized_decoded_bytes=0;self.max_serialized_decode_ratio=0.
    def recover(self,db,a,i,expected=None):
        row=db.execute("SELECT n,digest,payload FROM versions WHERE article=? AND ord=?",(a,i)).fetchone()
        if row is None:raise ValueError("missing wiki object")
        n,digest,ptr=row;blob=fetch_frame(self.file,ptr)
        art,bases=loads(blob)
        # Upstream retrieve_range uses an inclusive end. length=0 requests one revision.
        texts=retrieve_range(art,bases,i,0)
        if len(texts)!=1:raise ValueError("native retrieval cardinality")
        raw=texts[0].encode("utf8")
        if len(raw)!=n or h.sha(raw)!=digest:raise ValueError("wiki source mismatch")
        part=next(p for p in art.partitions() if i in p);prefix=part[:part.index(i)+1]
        # Prefix source volume is a logical proxy, not actual ndiff decoder traffic.
        dd=sum(db.execute("SELECT n FROM versions WHERE article=? AND ord=?",(a,j)).fetchone()[0] for j in prefix)
        # gzip JSON necessarily inflates the entire per-article artifact for this cold API path.
        serialized=len(gzip.decompress(blob))
        self.serialized_decoded_bytes+=serialized
        if n:self.max_serialized_decode_ratio=max(self.max_serialized_decode_ratio,serialized/n)
        return raw,len(blob),dd,len(prefix)-1

def export_wiki(db,file,events,manifest,mode):
    histories=collections.defaultdict(list)
    for g,(a,i,raw) in enumerate(events,1):
        assert len(histories[a])==i
        ts=datetime.datetime.fromtimestamp(manifest["origins"][g-1]["committer_unix"],datetime.timezone.utc).isoformat()
        histories[a].append(Revision(g,ts,raw.decode("utf8")))
    max_depth=0;anchors=0
    for a,revs in sorted(histories.items()):
        budget=None if mode=="default" else sum(len(x.text)*2 for x in revs)
        blob=create_wiki(a,revs,budget);off=file.tell();file.write(blob)
        art,bases=loads(blob)
        assert sorted(i for p in art.partitions() for i in p)==list(range(len(revs)))
        anchors+=len(art.anchors);max_depth=max(max_depth,max(len(p)-1 for p in art.partitions()))
        db.execute("UPDATE versions SET payload=? WHERE article=?",(PTR.pack(off,len(blob)),a))
    return dict(max_depth=max_depth,anchors=anchors)

def experiment(folder,events,manifest,ext):
    cuts=manifest["cutoffs"];refs={c:h.active_oracle(events,c) for c in cuts};qs=h.plan_queries(refs[cuts[0]])
    bodies={};results={}
    for policy in ("snapshot","bounded_anchor"):
        path=folder/(policy+".sqlite");db=h.integrated_setup(path,ext,manifest)
        for g,(a,i,raw) in enumerate(events,1):
            assert h.append_policy(db,a,raw,h.origin_tuple(manifest["origins"][g-1]),policy)==(g,i)
        size=h.compact(db,path);db.close();db=h.connect(path,ext)
        results[policy]=dict(**size,**verify_archive(db,events,manifest,qs,refs,bodies),total_archive_bytes=path.stat().st_size)
        db.close()
    import shutil
    for policy in ("snapshot_sidecar","bounded_anchor_sidecar","wiki_default","wiki_large_budget"):
        path=folder/(policy+".sqlite");side=folder/(policy+".bin")
        source="bounded_anchor" if policy.startswith("bounded") else "snapshot"
        shutil.copyfile(folder/(source+".sqlite"),path);db=h.connect(path,ext)
        extra={}
        with side.open("wb") as f:
            if policy.endswith("sidecar"):
                payload=export_frames(db,f)
                assert payload==results[source]["payload_bytes"]
            else:extra=export_wiki(db,f,events,manifest,"default" if policy=="wiki_default" else "large")
        db.execute("INSERT INTO corpus VALUES('source_codec',?)",(policy.encode(),))
        size=finalize(db,path);db.close();db=h.connect(path,ext)
        with side.open("rb") as f:
            reader=Frames(f) if policy.endswith("sidecar") else WikiReader(f)
            with patch.object(ve,"recover",reader.recover):
                measured=verify_archive(db,events,manifest,qs,refs,bodies)
            if policy.startswith("wiki"):
                extra.update(serialized_decoded_bytes_all_recoveries=reader.serialized_decoded_bytes,
                    max_serialized_decode_ratio=reader.max_serialized_decode_ratio)
                measured["logical_decode_metric"]="partition prefix source-volume proxy; gzip JSON inflation separately measured"
            else:
                assert measured["decode_amplification"]==results[source]["decode_amplification"]
                assert measured["activated_bytes"]==results[source]["activated_bytes"]
        db.close()
        results[policy]=dict(**extra,**measured,sqlite_bytes=size,sidecar_bytes=side.stat().st_size,total_archive_bytes=size+side.stat().st_size)
    for ref in refs.values():ref.close()
    return dict(policies=results,query_plan_sha256=h.sha(h.canonical([dict(phrases=p,op=o) for p,o in qs])).hex(),
        wikecd_version=importlib.metadata.version("wikecd"),revisions=len(events),documents=len(manifest["retained_paths"]))

def run(root,corpus,ext):
    if corpus in ("gitdocs","k8sdocs"):
        events,manifest=h.collect(root,corpus,window=800,cohort=160)
        frozen=HERE.parent/"round-132"/("results-"+corpus+"-800-132.json")
    else:
        sys.path.insert(0,str(HERE.parent/"round-131"))
        import budget_archive as old
        events,manifest=old.collect(root,corpus)
        frozen=HERE.parent/"round-129"/("results-"+corpus+".json")
    original=json.loads(frozen.read_text());assert h.sha(h.canonical(manifest)).hex()==original["manifest_sha256"]
    with tempfile.TemporaryDirectory() as d:result=experiment(Path(d),events,manifest,ext)
    for p in ("snapshot","bounded_anchor"):
        assert result["policies"][p]["total_archive_bytes"]==original["result"]["policies"][p]["sqlite_bytes"]
    assert result["query_plan_sha256"]==h.sha(h.canonical(original["result"]["query_plan"])).hex()
    return dict(round=135,corpus=corpus,manifest_sha256=original["manifest_sha256"],result=result,
      limits=["all sidecar representations finalized/read-only; no append/crash parity",
        "WikECD native gzip JSON serializer and native retrieve_range, default and larger heuristic budget",
        "WikECD source-volume proxy is not measured decoder byte traffic; complete gzip object activation and JSON inflation separately charged",
        "timing includes Python wrappers and full per-article load; no cached WikECD variant",
        "same lexical ranking and evidence contract; no claim of identical native WikECD ranking functionality"])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--corpus",required=True);p.add_argument("--extension",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    x=run(a.root,a.corpus,a.extension.resolve());a.out.write_text(json.dumps(x,indent=2)+"\n");print("RESULT_JSON="+json.dumps(x),flush=True)
