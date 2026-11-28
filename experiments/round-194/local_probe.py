import random,json,itertools,statistics
from selector import choose,totals

def brute(ranked,m,b,c,d):
    best=0
    for mask in range(1<<len(ranked)):
        ids=[r for i,r in enumerate(ranked) if mask>>i&1];x,y,_=totals(ids,m,b)
        if x<=c and y<=d:best=max(best,sum(1000000//(i+1) for i in range(len(ranked)) if mask>>i&1))
    return best

def run():
    results=[];checks=0;oracle=0
    for seed,group in itertools.product((194,195,196,197),(1,2,4,8)):
        rng=random.Random(seed);work=[]
        for j in range(200):
            lengths=[rng.randint(150,1800) for _ in range(32)];m={i:(i//group,n) for i,n in enumerate(lengths)}
            b={i//group:(sum(lengths[i:i+group]),sum(lengths[i:i+group])//2) for i in range(0,32,group)}
            ranked=rng.sample(range(32),10)
            for c,d in ((2048,4096),(4096,8192),(4096,32768)):
                row={};weights={r:1000000//(i+1) for i,r in enumerate(ranked)}
                for p in ('rank','context','shared','exact'):
                    out=choose(ranked,m,b,c,d,p);ctx,dec,enc=totals(out,m,b);assert ctx<=c and dec<=d and len(out)==len(set(out));checks+=1
                    row[p]=(sum(weights[r] for r in out),ctx,dec,len(out))
                assert row['exact'][0]>=max(row[p][0] for p in ('rank','context','shared'))
                if j<10:assert row['exact'][0]==brute(ranked,m,b,c,d);oracle+=1
                work.append(row)
        for p in ('rank','context','shared','exact'):
            rows=[x[p] for x in work];results.append(dict(seed=seed,group=group,policy=p,mean_utility=statistics.mean(x[0] for x in rows),mean_context=statistics.mean(x[1] for x in rows),mean_decode=statistics.mean(x[2] for x in rows),mean_count=statistics.mean(x[3] for x in rows),exact_match=sum(x[p][0]==x['exact'][0] for x in work),queries=len(work)))
    return dict(checks=checks,oracle_checks=oracle,results=results)
if __name__=='__main__':
    print(json.dumps(run(),indent=2))
