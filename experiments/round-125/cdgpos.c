/* Single-token FTS5 positional extraction via public API. */
#include <sqlite3ext.h>
#include <stdint.h>
SQLITE_EXTENSION_INIT1
static void offsets(const Fts5ExtensionApi *api,Fts5Context *fts,
                    sqlite3_context *ctx,int argc,sqlite3_value **argv){
    int n=0,rc,j;
    unsigned char *b;
    (void)argv;
    if(argc || api->xPhraseCount(fts)!=1 || api->xPhraseSize(fts,0)!=1 || api->xColumnCount(fts)!=1){
        sqlite3_result_error(ctx,"single token/column required",-1);return;
    }
    rc=api->xInstCount(fts,&n);
    if(rc!=SQLITE_OK){sqlite3_result_error_code(ctx,rc);return;}
    if(n<=0 || n>16777216){sqlite3_result_error(ctx,"invalid position count",-1);return;}
    b=sqlite3_malloc64((sqlite3_uint64)n*4);
    if(!b){sqlite3_result_error_nomem(ctx);return;}
    for(j=0;j<n;j++){
        int phrase,col,off;
        uint32_t v;
        rc=api->xInst(fts,j,&phrase,&col,&off);
        if(rc!=SQLITE_OK || phrase!=0 || col!=0 || off<0){
            sqlite3_free(b);
            sqlite3_result_error(ctx,"invalid occurrence",-1);return;
        }
        v=(uint32_t)off;
        b[4*j]=(unsigned char)v;b[4*j+1]=(unsigned char)(v>>8);
        b[4*j+2]=(unsigned char)(v>>16);b[4*j+3]=(unsigned char)(v>>24);
    }
    sqlite3_result_blob64(ctx,b,(sqlite3_uint64)n*4,sqlite3_free);
}
int sqlite3_cdgpos_init(sqlite3 *db,char **err,const sqlite3_api_routines *api){
    sqlite3_stmt *st=0;fts5_api *fts=0;int rc;
    SQLITE_EXTENSION_INIT2(api);
    rc=sqlite3_prepare_v2(db,"SELECT fts5(?1)",-1,&st,0);
    if(rc==SQLITE_OK)rc=sqlite3_bind_pointer(st,1,&fts,"fts5_api_ptr",0);
    if(rc==SQLITE_OK){int step=sqlite3_step(st);if(step!=SQLITE_ROW)rc=step;}
    sqlite3_finalize(st);
    if(rc!=SQLITE_OK || !fts){*err=sqlite3_mprintf("FTS5 API unavailable");return SQLITE_ERROR;}
    return fts->xCreateFunction(fts,"cdg_offsets",0,offsets,0);
}
