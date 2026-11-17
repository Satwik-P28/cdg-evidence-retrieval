#!/usr/bin/env python3
"""R62: independently pinned public version histories, source bytes verified.

Authentic upstream file history is fetched by immutable commit SHA. Only compact
hashes and measurements are committed, not third-party README text.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, re, statistics, sys, time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from urllib.parse import quote

HERE=Path(__file__).resolve().parent
R58=HERE.parent/'round-58'/'mixed_archive.py'
R54=HERE.parent/'round-54'/'heldout_dev.py'
R46=HERE.parent/'round-46'/'version_chunks.py'
R47=HERE.parent/'round-47'/'manifest_lab.py'
PINNED={
  'ruff':{'repo':'astral-sh/ruff','cutoff':'9e7e7a47f1b866340c432d535c41693d6beb4621','path':'README.md','license':'MIT'},
  'transformers':{'repo':'huggingface/transformers','cutoff':'fc00b5b3c9f9306c55908bb546fa3b033a4bfb1d','path':'README.md','license':'Apache-2.0'},
  'flask':{'repo':'pallets/flask','cutoff':'49943b5a94413a530761350f04e896f76e8d620e','path':'README.md','license':'BSD-3-Clause'},
}
POLICIES=('all_whole','all_gear512','known_cohort','online_read_weighted')
IND_COUNTS=(0,128,512)


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name]=obj
    spec.loader.exec_module(obj)
    return obj


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def git_blob_sha(blob):
    return hashlib.sha1(f'blob {len(blob)}\0'.encode()+blob).hexdigest()


def get(url,limit=500_000):
    with urlopen(Request(url,headers={'User-Agent':'CDG-version-history-replication/1.0',
                                      'Accept':'application/vnd.github+json'}),
                 timeout=60) as res:
        value=res.read(limit+1)
    if len(value)>limit:raise ValueError('upstream source exceeds size cap')
    return value


def download_history(spec,count=12,get_fn=get):
    repo,cutoff,path=spec['repo'],spec['cutoff'],spec['path']
    if not re.fullmatch(r'[0-9a-f]{40}',cutoff):
        raise ValueError('history HEAD must be pinned to a full Git commit')
    if '/' not in repo or path.startswith('/') or '..' in path:
        raise ValueError('untrusted repository path')
    api=f'https://api.github.com/repos/{repo}/commits?sha={cutoff}&path={quote(path)}&per_page=48'
    entries=json.loads(get_fn(api))
    if not isinstance(entries,list) or len(entries)<3:
        raise ValueError(f'{repo}: fewer than three historical README commits at pinned cutoff')
    chosen=[]
    seen=set()
    for obj in entries:
        commit=obj['sha']
        if not re.fullmatch(r'[0-9a-f]{40}',commit):raise ValueError('bad commit id')
        if commit in seen:raise ValueError('duplicate commit from history API')
        seen.add(commit)
        url=f'https://raw.githubusercontent.com/{repo}/{commit}/{path}'
        try:
            raw=get_fn(url)
        except HTTPError as error:
            if error.code==404:
                # A path-history event can represent the original deletion or
                # a later rename. These revisions have no available README blob.
                continue
            raise
        if b'\0' in raw or len(raw)>500_000 or not raw:
            raise ValueError('invalid README source bytes')
        digest=sha(raw)
        if chosen and digest==chosen[-1]['sha256']:
            # A commit listed for the file may have changed only mode/metadata.
            continue
        chosen.append({
            'commit':commit,
            'sha256':digest,'git_blob':git_blob_sha(raw),
            'bytes':len(raw),'data':raw,
            'date':obj.get('commit',{}).get('committer',{}).get('date','')})
        if len(chosen)==count:break
    if len(chosen)<3:
        raise ValueError(f'{repo}: fewer than three distinct historical README content versions')
    chosen.reverse()
    if len({x['sha256'] for x in chosen})<3:
        raise ValueError('history lacks multiple changes')
    return chosen


def history_identity(records):
    text='\n'.join(f"{x['commit']}:{x['git_blob']}:{x['sha256']}" for x in records)
    return sha(text.encode())


def input_sources(history_docs):
    r54=load('cdg54_input_r62',R54)
    dev=r54.locked_sample(r54.load_development())
    # Source paragraphs from question IDs 256:384, not from R58's first 128.
    rows=dev[256:384]
    independent=[('independent',''.join(sentences).encode('utf8'))
                 for row in rows for _,sentences in row['context']]
    if len(independent)<max(IND_COUNTS):raise ValueError('insufficient independent docs')
    return independent,sha('\n'.join(sorted(str(r['_id']) for r in rows)).encode())


def run_matrix(histories,independent,ids_digest):
    r58=load('cdg58_r62',R58)
    r46=load('cdg46_r62',R46)
    r47=load('cdg47_r62',R47)
    out=[]
    for name,versions in histories.items():
        h=[('history',x['data']) for x in versions]
        for n in IND_COUNTS:
            docs=h+independent[:n]
            record={'history':name,'history_count':len(h),'independent_count':n,
                    'policies':{}}
            for policy in POLICIES:
                store=r58.MixedStore(docs,policy,r46.frame,r47)
                spans=store.read_statistics(questions_per_source=2)
                record['policies'][policy]={
                    'archive_bytes':store.archive_bytes(),
                    'mean_compressed_span_bytes':spans['mean_compressed_frame_bytes'],
                    'method_counts':{'whole':store.methods.count('whole'),
                                     'gear512':store.methods.count('gear512')},
                    'unique_frames':len(store.payloads)}
            baseline=record['policies']['all_whole']
            for _,metric in record['policies'].items():
                metric['archive_delta_pct_vs_whole']=round(
                    100*(metric['archive_bytes']/baseline['archive_bytes']-1),3)
                metric['read_delta_pct_vs_whole']=round(
                    100*(metric['mean_compressed_span_bytes']/
                         baseline['mean_compressed_span_bytes']-1),3)
            out.append(record)
    return {
        'input_provenance':{
            key:{
                'repository':PINNED[key]['repo'],'cutoff_commit':PINNED[key]['cutoff'],
                'file':PINNED[key]['path'],'license':PINNED[key]['license'],
                'history_identity_sha256':history_identity(versions),
                'requested_version_limit':12,
                'actual_distinct_versions':len(versions),
                'versions':[ {key:x[key] for key in ('commit','sha256','git_blob','bytes','date')}
                             for x in versions ]
            } for key,versions in histories.items()},
        'independent_sample_question_id_sha256':ids_digest,
        'scenarios':out,
        'limitations':[
            'up to 12 distinct revisions per repository: fewer changes are retained and reported rather than padded',
            'one history each from Ruff, Transformers and Flask; these are original upstream README files, not random versioned source families',
            'GitHub commit API output is cut off at fixed immutable commit SHAs, and exact source content hashes are recorded',
            'no upstream source bytes redistributed',
            'independent question-local source paragraphs are from HotpotQA dev used in earlier extraction rounds; this is not wholly new domain',
            'R58 online layout objective frozen before these upstream histories were collected',
            'only Zlib6 frame layouts; strong Zstandard and Git pack controls in R60 on previous mixture',
            'all read bytes are logical compressed frame activation under seeded random source spans, not physical SSD I/O',
            'no FTS/model/verifier cost or factual retrieval metric']}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',default=str(HERE/'ci-results.json'))
    args=parser.parse_args()
    histories={name:download_history(spec) for name,spec in PINNED.items()}
    independent,sample_id=input_sources(histories)
    results=run_matrix(histories,independent,sample_id)
    Path(args.out).write_text(json.dumps(results,indent=2,ensure_ascii=False)+'\n')
    print('ROUND62',json.dumps({
        'history':{key:{'versions':len(rows),
                        'sha256':history_identity(rows),
                        'total_bytes':sum(len(x['data']) for x in rows)}
                   for key,rows in histories.items()},
        'mixtures':[{ 'history':x['history'],'independent':x['independent_count'],
                      'online':x['policies']['online_read_weighted'],
                      'whole_archive_bytes':x['policies']['all_whole']['archive_bytes'],
                      'cohort_archive_bytes':x['policies']['known_cohort']['archive_bytes']}
                     for x in results['scenarios']]},sort_keys=True))


if __name__=='__main__':main()
