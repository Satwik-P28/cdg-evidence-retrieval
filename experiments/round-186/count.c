#include <sqlite3ext.h>
SQLITE_EXTENSION_INIT1
static void cnt(const Fts5ExtensionApi *a,Fts5Context *f,sqlite3_context *c,int n,sqlite3_value **v){int k=0; (void)n;(void)v;int rc=a->xInstCount(f,&k);if(rc==SQLITE_OK)sqlite3_result_int(c,k);else sqlite3_result_error_code(c,rc);}
int sqlite3_extension_init(sqlite3 *db,char **err,const sqlite3_api_routines *api){(void)err;SQLITE_EXTENSION_INIT2(api);fts5_api *f=0;sqlite3_stmt *s=0;int rc=sqlite3_prepare_v2(db,"SELECT fts5(?1)",-1,&s,0);if(rc!=SQLITE_OK)return rc;sqlite3_bind_pointer(s,1,&f,"fts5_api_ptr",0);sqlite3_step(s);sqlite3_finalize(s);return f?f->xCreateFunction(f,"r186_count",0,cnt,0):SQLITE_ERROR;}
