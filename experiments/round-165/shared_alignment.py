"""Lossless byte copy/literal script from a shared normalized-token alignment."""
import struct

def offsets(db,raw,ts):
    blob=db.execute("SELECT cdg_token_offsets(?)",(raw.decode("utf8"),)).fetchone()[0]
    assert len(blob)==8*len(ts)
    spans=list(struct.iter_unpack(">II",blob))
    prev=0
    for a,b in spans:
        assert prev<=a<b<=len(raw)
        prev=b
    return spans

def make_script(old,raw,old_spans,new_spans,ops):
    # Token cells extend from native token start to next token start; leading
    # non-token bytes are separate. All copies verified byte-for-byte.
    a=[p[0] for p in old_spans]+[len(old)]
    b=[p[0] for p in new_spans]+[len(raw)]
    segments=[]
    def literal(data):
        if not data:return
        if segments and segments[-1][0]==0:segments[-1][1].extend(data)
        else:segments.append((0,bytearray(data),0))
    def copy(pos,n):
        if not n:return
        if segments and segments[-1][0]==1 and segments[-1][1]+segments[-1][2]==pos:
            _,p,m=segments[-1];segments[-1]=(1,p,m+n)
        else:segments.append((1,pos,n))
    def matched(x,y,z,w):
        if old[x:y]==raw[z:w]:copy(x,y-x)
        else:literal(raw[z:w])
    matched(0,a[0],0,b[0])
    pa=pb=0
    for op,i,j,k,l in ops:
        assert i==pa and k==pb and i<=j<len(a) and k<=l<len(b)
        if op=="equal":
            assert j-i==l-k
            for x,y in zip(range(i,j),range(k,l)):matched(a[x],a[x+1],b[y],b[y+1])
        else:literal(raw[b[k]:b[l]])
        pa,pb=j,l
    assert pa==len(a)-1 and pb==len(b)-1
    out=bytearray()
    for tag,x,n in segments:
        if tag:out.extend(struct.pack(">BII",1,x,n))
        else:out.extend(struct.pack(">BI",0,len(x)));out.extend(x)
    assert len(out)<=10*len(raw)+64
    return bytes(out)

def decode_script(old,script,n):
    if n<0:raise ValueError("negative output size")
    out=bytearray();i=0
    while i<len(script):
        tag=script[i];i+=1
        if tag==0:
            if i+4>len(script):raise ValueError("truncated literal")
            size=struct.unpack_from(">I",script,i)[0];i+=4
            if size==0 or i+size>len(script) or len(out)+size>n:raise ValueError("invalid literal")
            out.extend(script[i:i+size]);i+=size
        elif tag==1:
            if i+8>len(script):raise ValueError("truncated copy")
            pos,size=struct.unpack_from(">II",script,i);i+=8
            if size==0 or pos+size>len(old) or len(out)+size>n:raise ValueError("invalid copy")
            out.extend(old[pos:pos+size])
        else:raise ValueError("invalid opcode")
    if len(out)!=n:raise ValueError("wrong output size")
    return bytes(out)
