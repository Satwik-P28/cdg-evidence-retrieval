"""Exact block activation / context-byte selection, no gold labels in utility."""
from fractions import Fraction


def totals(ids, meta, blocks):
    active={meta[r][0] for r in ids}
    return sum(meta[r][1] for r in ids),sum(blocks[b][0] for b in active),sum(blocks[b][1] for b in active)


def choose(ranked,meta,blocks,context,decode,policy):
    ranked=tuple(ranked)
    if len(ranked)!=len(set(ranked)) or len(ranked)>10:raise ValueError('unique top ten only')
    w={r:1000000//(i+1) for i,r in enumerate(ranked)}
    if policy=='exact':
        best=(0,0,0,0);out=()
        def visit(i,selected,active,c,d,u,mask):
            nonlocal best,out
            if i==len(ranked):
                score=(u,-d,-c,-mask)
                if score>best:best=score;out=selected
                return
            visit(i+1,selected,active,c,d,u,mask)
            r=ranked[i];b,n=meta[r];new=blocks[b][0] if b not in active else 0
            if c+n<=context and d+new<=decode:
                visit(i+1,selected+(r,),active|{b},c+n,d+new,u+w[r],mask|(1<<i))
        visit(0,(),set(),0,0,0,0);return list(out)
    if policy not in ('rank','context','shared'):raise ValueError('unknown policy')
    out=[];active=set();c=d=0
    while True:
        opts=[]
        for i,r in enumerate(ranked):
            if r in out:continue
            b,n=meta[r];new=blocks[b][0] if b not in active else 0
            if c+n>context or d+new>decode:continue
            if policy=='rank':gain=Fraction(-i)
            elif policy=='context':gain=Fraction(w[r],max(1,n))
            else:gain=Fraction(w[r]*context*decode,max(1,n*decode+new*context))
            opts.append((gain,-i,r,b,n,new))
        if not opts:break
        _,_,r,b,n,new=max(opts);out.append(r);active.add(b);c+=n;d+=new
    return [r for r in ranked if r in out]
