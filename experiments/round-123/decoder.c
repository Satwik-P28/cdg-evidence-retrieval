/* R123: bounded native lookup and active interval filter for R122 wire format.
 * No new codec. Input is an immutable build-validated block. The selected
 * posting list is checked in full; unrelated entries are structurally scanned.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
static int rv(const unsigned char *b,size_t n,size_t *p,uint32_t *v){
    uint32_t x=0; unsigned i;
    for(i=0;i<5;i++){
        unsigned y;
        if(*p>=n)return -1;
        y=b[(*p)++];
        if(i==4 && (y&0xf0))return -1;
        x|=(uint32_t)(y&127)<<(7*i);
        if(y<128){
            if(i && y==0)return -1;
            *v=x;return 0;
        }
    }
    return -1;
}
static int filter(const unsigned char *b,size_t n,const uint32_t *g,
                  const uint32_t *o,size_t cap,uint32_t *out,size_t *seen){
    size_t p=0,used=0;uint32_t count,a=0,last_a=0,last_end=0,j;
    if(rv(b,n,&p,&count)||count>(n-p)/4)return -2;
    *seen=count;
    for(j=0;j<count;j++){
        uint32_t da,s,span,tf,e;
        if(rv(b,n,&p,&da)||rv(b,n,&p,&s)||rv(b,n,&p,&span)||rv(b,n,&p,&tf))return -2;
        if(da>UINT32_MAX-a||span>UINT32_MAX-s||!span||!tf)return -2;
        a+=da;e=s+span;
        if(!a||a>=cap||(a==last_a && s<last_end))return -2;
        if(g[a] && s<=o[a] && o[a]<e){
            if(used>=cap|| (used && out[(used-1)*2]==g[a]))return -2;
            out[used*2]=g[a];out[used*2+1]=tf;used++;
        }
        last_a=a;last_end=e;
    }
    if(p!=n)return -2;
    return (int)used;
}
int cdg_lookup(const unsigned char *b,size_t n,const unsigned char *term,size_t tn,
               const uint32_t *g,const uint32_t *o,size_t cap,uint32_t *out,
               size_t *seen){
    uint32_t count,j;size_t p=0,prev_n=0;int result=0,found=0;
    unsigned char *prev;
    *seen=0;
    if(!n||n>16*1024*1024||!cap||cap>10000000||rv(b,n,&p,&count)||count>(n-p)/3)return -1;
    prev=malloc(n+1);
    if(!prev)return -3;
    for(j=0;j<count;j++){
        uint32_t pre,suffix,len;
        if(rv(b,n,&p,&pre)||rv(b,n,&p,&suffix)||pre>prev_n||suffix>n-p){result=-1;goto done;}
        memcpy(prev+pre,b+p,suffix);prev_n=(size_t)pre+suffix;p+=suffix;
        if(rv(b,n,&p,&len)||len>n-p||len<1){result=-1;goto done;}
        if(prev_n==tn&&!memcmp(prev,term,tn)){
            if(found||b[p]!=0){result=-1;goto done;}
            result=filter(b+p+1,len-1,g,o,cap,out,seen);found=1;
            if(result<0)goto done;
        }
        p+=len;
    }
    if(p!=n)result=-1;
done:
    free(prev);return result;
}
