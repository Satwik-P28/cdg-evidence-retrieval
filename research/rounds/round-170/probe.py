import ctypes as C, ctypes.util, random, struct, sqlite3, tempfile, pathlib, json
z=C.CDLL(ctypes.util.find_library('zstd')); z.ZSTD_compressBound.argtypes=[C.c_size_t];z.ZSTD_compressBound.restype=C.c_size_t;z.ZSTD_compress.argtypes=[C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t,C.c_int];z.ZSTD_compress.restype=C.c_size_t;z.ZSTD_isError.argtypes=[C.c_size_t];z.ZSTD_isError.restype=C.c_uint

def compress(raw):
    dst=C.create_string_buffer(z.ZSTD_compressBound(len(raw)));n=z.ZSTD_compress(dst,len(dst),raw,len(raw),3);assert not z.ZSTD_isError(n);return dst.raw[:n]
def enc(a):return struct.pack('<'+'I'*len(a),*a)
def count(raw,needle):
    n=pos=0
    while True:
        i=raw.find(needle,pos)
        if i<0:return n
        n+=i%4==0;pos=i+1
rng=random.Random(170)
for _ in range(10000):
    pool=[1,2,256,65536,16777216,0x02000100]; a=[rng.choice(pool) for _ in range(rng.randrange(120))]; p=[rng.choice(pool) for _ in range(rng.randrange(1,9))]; assert count(enc(a),enc(p))==sum(a[i:i+len(p)]==p for i in range(len(a)-len(p)+1))
print('10000 exact count checks')
with tempfile.TemporaryDirectory() as td:
  for v in [100,1000,10000]:
    terms=[f'token{i:06d}'.encode() for i in range(v)]; docs=[[rng.randrange(v) for _ in range(500)] for _ in range(1000)]; sizes={}
    for mode in ['text','ids']:
      path=pathlib.Path(td)/f'{v}-{mode}.db';db=sqlite3.connect(path);db.execute('CREATE TABLE tape(cid INTEGER PRIMARY KEY,n INTEGER,z INTEGER,body BLOB)');db.execute('CREATE TABLE lexicon(tid INTEGER PRIMARY KEY,term BLOB)');db.executemany('INSERT INTO lexicon VALUES(?,?)',enumerate(terms,1));payload=0
      for cid,seq in enumerate(docs,1):
        raw=b' '.join(terms[i] for i in seq) if mode=='text' else enc([i+1 for i in seq]);cmp=compress(raw);body=min([raw,cmp],key=len);payload+=len(body);db.execute('INSERT INTO tape VALUES(?,?,?,?)',(cid,len(raw),int(len(cmp)<len(raw)),body))
      db.commit();db.execute('VACUUM');db.close();sizes[mode]={'file':path.stat().st_size,'payload':payload}
    print(v,json.dumps(sizes))
