import ctypes as C, ctypes.util, random, sqlite3, tempfile, pathlib, struct, collections
z=C.CDLL(ctypes.util.find_library('zstd'))
for fn,args,result in [('ZSTD_compressBound',[C.c_size_t],C.c_size_t),('ZSTD_createCCtx',[],C.c_void_p),('ZSTD_freeCCtx',[C.c_void_p],C.c_size_t),('ZSTD_createDCtx',[],C.c_void_p),('ZSTD_freeDCtx',[C.c_void_p],C.c_size_t),('ZSTD_compress_usingDict',[C.c_void_p,C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t,C.c_int],C.c_size_t),('ZSTD_decompress_usingDict',[C.c_void_p,C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t],C.c_size_t),('ZSTD_isError',[C.c_size_t],C.c_uint)]:
    f=getattr(z,fn);f.argtypes=args;f.restype=result
def enc(raw,base=b''):
    dst=C.create_string_buffer(z.ZSTD_compressBound(len(raw)));ctx=z.ZSTD_createCCtx();n=z.ZSTD_compress_usingDict(ctx,dst,len(dst),raw,len(raw),base,len(base),3);z.ZSTD_freeCCtx(ctx);assert not z.ZSTD_isError(n);return dst.raw[:n]
def dec(frame,n,base=b''):
    dst=C.create_string_buffer(n);ctx=z.ZSTD_createDCtx();size=z.ZSTD_decompress_usingDict(ctx,dst,n,frame,len(frame),base,len(base));z.ZSTD_freeDCtx(ctx);assert not z.ZSTD_isError(size) and size==n;return dst.raw[:n]
def run(path,docs,delta):
    db=sqlite3.connect(path);db.execute('CREATE TABLE tape(cid INTEGER PRIMARY KEY,n INTEGER NOT NULL,z INTEGER NOT NULL,base INTEGER NOT NULL,body BLOB NOT NULL)');hist=collections.defaultdict(list);full={};stats=collections.Counter()
    for cid,(article,raw) in enumerate(docs,1):
        frame=enc(raw);body,zflag=(frame,1) if len(frame)<len(raw) else (raw,0);best=(len(body),0,zflag,body)
        if delta:
            for parent in hist[article][-4:]:
                pr,pb,pz=full[parent]
                if 2*(len(raw)+len(pr))>5*len(raw):continue
                d=enc(raw,pr)
                if 5*len(d)>4*len(body) or 2*(len(pb)+len(d))>3*len(body):continue
                if len(d)+8<best[0]:best=(len(d)+8,parent,2,d)
        _,parent,flag,body=best
        if not parent:full[cid]=(raw,body,flag);hist[article].append(cid)
        else:stats['delta']+=1
        stats['payload']+=len(body);db.execute('INSERT INTO tape VALUES(?,?,?,?,?)',(cid,len(raw),flag,parent,body))
    db.commit();db.execute('VACUUM');db.close();db=sqlite3.connect(path)
    for cid,(_,want) in enumerate(docs,1):
        n,flag,parent,body=db.execute('SELECT n,z,base,body FROM tape WHERE cid=?',(cid,)).fetchone();ab=len(body);dd=n
        if parent:
            pn,pflag,pbase,pbody=db.execute('SELECT n,z,base,body FROM tape WHERE cid=?',(parent,)).fetchone();assert pbase==0 and pflag in (0,1);old=dec(pbody,pn) if pflag else pbody;raw=dec(body,n,old);ab+=len(pbody);dd+=pn
        else:raw=dec(body,n) if flag else body
        assert raw==want and 2*dd<=5*len(raw) and 2*ab<=3*min(len(raw),len(enc(raw)));stats['checks']+=1
    db.close();return path.stat().st_size,dict(stats)
if __name__=='__main__':
    rng=random.Random(171)
    with tempfile.TemporaryDirectory() as d:
        for changes in (1,20,150,500):
            seqs=[]
            for article in range(100):
                a=[rng.randrange(1,20001) for _ in range(500)]
                for v in range(10):
                    if v:
                        for j in rng.sample(range(500),changes):a[j]=rng.randrange(1,20001)
                    seqs.append((article,a[:]))
            for mode in ('text','ids'):
                docs=[(article,b' '.join(f'token{x:05d}'.encode() for x in a) if mode=='text' else struct.pack('<'+'I'*len(a),*a)) for article,a in seqs]
                print(changes,mode,[run(pathlib.Path(d)/f'{changes}-{mode}-{delta}.db',docs,delta) for delta in (False,True)],flush=True)
