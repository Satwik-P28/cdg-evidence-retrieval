#!/usr/bin/env python3
"""Test whether source-family aware document-frequency can correct IDF bias in redundant revision histories.
Not a neural model. Train/test split by deterministic SHA hash for fusion preference."""
import sys,json,time
from pathlib import Path
import numpy as np
from scipy import sparse
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from round5_anchor_budget import prep_data,eval_rank,index_size
samples,vec,F,D,Q=prep_data()
N,V=F.shape
families=sorted(set(s['path'] for s in samples))
fam_index=np.array([families.index(s['path']) for s in samples])
G=len(families)
train=np.array([i for i,s in enumerate(samples) if int(s['sha'][-4:],16)%5<2]); test=np.array([i for i in range(N) if i not in set(train)])

def idfs_by_family(C):
    C=C.tocsr()
    familyrows=sparse.csr_matrix((np.ones(N,dtype=np.int8),(fam_index,np.arange(N))),shape=(G,N))
    grouped=(familyrows@C.sign()).tocsr()
    return np.asarray((grouped>0).sum(axis=0)).reshape(-1)

def bm25_mod(C,alpha=0):
    C=C.tocsr().astype('float32')
    lengths=np.asarray(C.sum(axis=1)).ravel();mean=max(float(lengths.mean()),1)
    df=np.bincount(C.indices,minlength=V)
    fdf=idfs_by_family(C)
    idf0=np.log(1+(N-df+.5)/(df+.5))
    idf1=np.log(1+(G-fdf+.5)/(fdf+.5))
    idf=(1-alpha)*idf0+alpha*idf1
    vals=C.copy()
    ln=np.repeat(lengths,np.diff(C.indptr))
    vals.data=(vals.data*2.2/(vals.data+1.2*(.25+.75*ln/mean)))*idf[vals.indices]
    return vals
out={'corpus':{'versions':N,'families':G,'vocab':V},'alpha':{}}
for a in [0,.25,.5,.75,1]:
    WX=bm25_mod(F,a);WD=bm25_mod(D,a)
    Sf=(Q@WX.T).toarray();Sd=(Q@WD.T).toarray()
    Sm=(Q@(WX+WD).T).toarray()
    # Source and changed region indexed one table, no query-time reweighting
    out['alpha'][str(a)]={'full':{'train':eval_rank(Sf,train),'test':eval_rank(Sf,test)},
      'diff':{'train':eval_rank(Sd,train),'test':eval_rank(Sd,test)},
      'merged':{'train':eval_rank(Sm,train),'test':eval_rank(Sm,test)},
      'index_bytes':index_size(WX+WD)}
    print('family alpha',a,'train hit5',out['alpha'][str(a)]['merged']['train']['hit5'],'test hit5',out['alpha'][str(a)]['merged']['test']['hit5'],flush=True)
trainbest=max(out['alpha'],key=lambda a:(out['alpha'][a]['merged']['train']['hit5'],out['alpha'][a]['merged']['train']['mrr10']))
out['train_selected_alpha']=trainbest;out['heldout_hit5_for_selected']=out['alpha'][trainbest]['merged']['test']['hit5']
(ROOT/'round5_family_idf_results.json').write_text(json.dumps(out,indent=2))
