"""R169 independent ASCII-token synthetic negative control; system libzstd."""
import collections,ctypes as C,ctypes.util,pathlib,random,re,sys
from rapidfuzz.distance import Levenshtein
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[3]/"experiments"/"round-165"))
from shared_alignment import make_script,decode_script
z=C.CDLL(ctypes.util.find_library("zstd"))
z.ZSTD_compressBound.argtypes=[C.c_size_t];z.ZSTD_compressBound.restype=C.c_size_t
z.ZSTD_createCCtx.restype=C.c_void_p
z.ZSTD_freeCCtx.argtypes=[C.c_void_p];z.ZSTD_freeCCtx.restype=C.c_size_t
z.ZSTD_compress_usingDict.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t,C.c_int];z.ZSTD_compress_usingDict.restype=C.c_size_t
z.ZSTD_isError.argtypes=[C.c_size_t];z.ZSTD_isError.restype=C.c_uint
def compress(raw,dict_bytes=b""):
    ctx=z.ZSTD_createCCtx();dst=C.create_string_buffer(z.ZSTD_compressBound(len(raw)))
    n=z.ZSTD_compress_usingDict(ctx,dst,len(dst),raw,len(raw),dict_bytes,len(dict_bytes),3)
    assert not z.ZSTD_isError(n);z.ZSTD_freeCCtx(ctx)
    return dst.raw[:n]
def tokenize(raw):
    ms=list(re.finditer(rb"[A-Za-z0-9]+",raw))
    return [m.group().lower() for m in ms],[m.span() for m in ms]
def script_for(a,b):
    ta,aa=tokenize(a);tb,bb=tokenize(b);ids={t:i for i,t in enumerate(dict.fromkeys(ta+tb))}
    ops=Levenshtein.opcodes([ids[t] for t in ta],[ids[t] for t in tb])
    s=make_script(a,b,aa,bb,ops);assert decode_script(a,s,len(b))==b;return s
def main():
    rng=random.Random(169)
    for _ in range(500):
        a=bytes(rng.choice(b"abcABC12 !\n,") for _ in range(rng.randrange(160)))
        b=bytearray(a)
        for j in range(8):
            i=rng.randrange(len(b)+1);b[i:i+rng.randrange(6)]=bytes(rng.choice(b"abcABC12 !\n,") for _ in range(rng.randrange(6)))
        script_for(a,bytes(b))
    print("random_byte_pairs_passed",500)
    for regime in ("single_replacement","scattered_replacements","case_spacing","large_insert"):
        total=collections.Counter()
        for i in range(200):
            a=[f"word{rng.randrange(100000)}".encode() for _ in range(600)]
            b=a.copy();old=b" ".join(a)
            if regime=="single_replacement":b[300]=b"newword"
            elif regime=="scattered_replacements":
                for j in rng.sample(range(600),20):b[j]=b"newword"+str(j).encode()
            elif regime=="case_spacing":
                for j in rng.sample(range(600),50):b[j]=b[j].upper()
            else:b[300:300]=[f"insert{j}".encode() for j in range(60)]
            raw=b" ".join(b)
            if regime=="case_spacing":raw=raw.replace(b" ",b"  ")
            script=script_for(old,raw);df=compress(raw,old);sf=compress(script);full=compress(raw);parent=compress(old)
            eligible=2*(len(old)+len(raw)+len(script))<=5*len(raw) and 5*len(sf)<=4*len(full) and 2*(len(parent)+len(sf))<=3*len(full)
            total.update(pairs=1,dict_bytes=len(df),script_bytes=len(sf),script_raw_bytes=len(script),script_smaller=int(len(sf)<len(df)),eligible=int(eligible),wins_eligible=int(len(sf)<len(df) and eligible))
        print(regime,dict(total))
if __name__=="__main__":main()
