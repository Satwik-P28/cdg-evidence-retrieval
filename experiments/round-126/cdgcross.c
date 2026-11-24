/* Exact single-phrase count whose start is on the left of a fragment boundary
 * and whose end crosses it. The left window belongs only to the start-owner
 * fragment; the right window may contain tokens from multiple fragments.
 */
#include <sqlite3ext.h>
SQLITE_EXTENSION_INIT1
static void crossing(const Fts5ExtensionApi *api,Fts5Context *fts,
                     sqlite3_context *ctx,int argc,sqlite3_value **argv){
    int left,k,n=0,rc,j,tf=0;
    if(argc!=1 || api->xPhraseCount(fts)!=1 || api->xColumnCount(fts)!=1){
        sqlite3_result_error(ctx,"one phrase and boundary offset required",-1);return;
    }
    left=sqlite3_value_int(argv[0]);k=api->xPhraseSize(fts,0);
    if(left<1||left>2||k<2||k>3){sqlite3_result_error(ctx,"invalid boundary or phrase length",-1);return;}
    rc=api->xInstCount(fts,&n);
    if(rc!=SQLITE_OK){sqlite3_result_error_code(ctx,rc);return;}
    for(j=0;j<n;j++){
        int p,col,off;
        rc=api->xInst(fts,j,&p,&col,&off);
        if(rc!=SQLITE_OK||p!=0||col!=0||off<0||off>3){
            sqlite3_result_error(ctx,"invalid boundary occurrence",-1);return;
        }
        if(off<left&&off+k>left)tf++;
    }
    sqlite3_result_int(ctx,tf);
}
int sqlite3_cdgcross_init(sqlite3 *db,char **err,const sqlite3_api_routines *api){
    sqlite3_stmt *st=0;fts5_api *fts=0;int rc;
    SQLITE_EXTENSION_INIT2(api);
    rc=sqlite3_prepare_v2(db,"SELECT fts5(?1)",-1,&st,0);
    if(rc==SQLITE_OK)rc=sqlite3_bind_pointer(st,1,&fts,"fts5_api_ptr",0);
    if(rc==SQLITE_OK){int step=sqlite3_step(st);if(step!=SQLITE_ROW)rc=step;}
    sqlite3_finalize(st);
    if(rc!=SQLITE_OK||!fts){*err=sqlite3_mprintf("FTS5 API unavailable");return SQLITE_ERROR;}
    return fts->xCreateFunction(fts,"cdg_cross",0,crossing,0);
}
