/* Native FTS5 one-phrase count control, using public SQLite extension API. */
#include <sqlite3ext.h>
SQLITE_EXTENSION_INIT1

static void phrase_count(const Fts5ExtensionApi *api,Fts5Context *fts,
                         sqlite3_context *ctx,int argc,sqlite3_value **argv){
    int n=0,rc;
    (void)argv;
    if(argc!=0 || api->xPhraseCount(fts)!=1 || api->xColumnCount(fts)!=1){
        sqlite3_result_error(ctx,"expected one unweighted phrase and one column",-1);
        return;
    }
    rc=api->xInstCount(fts,&n);
    if(rc!=SQLITE_OK){sqlite3_result_error_code(ctx,rc);return;}
    if(n<1){sqlite3_result_error(ctx,"missing phrase occurrences",-1);return;}
    sqlite3_result_int(ctx,n);
}

static void row_length(const Fts5ExtensionApi *api,Fts5Context *fts,
                       sqlite3_context *ctx,int argc,sqlite3_value **argv){
    int n=0,rc;
    (void)argv;
    if(argc!=0 || api->xColumnCount(fts)!=1){
        sqlite3_result_error(ctx,"expected one column",-1);return;
    }
    rc=api->xColumnSize(fts,-1,&n);
    if(rc!=SQLITE_OK){sqlite3_result_error_code(ctx,rc);return;}
    sqlite3_result_int(ctx,n);
}

/* Count phrase starts owned by the non-overlapping core, not its right halo. */
static void owned_count(const Fts5ExtensionApi *api,Fts5Context *fts,
                       sqlite3_context *ctx,int argc,sqlite3_value **argv){
    int n=0,rc,i,phrase,col,off,count=0,core=0,dl=0;
    if(argc!=1 || api->xPhraseCount(fts)!=1 || api->xColumnCount(fts)!=1){
        sqlite3_result_error(ctx,"expected one phrase and core length",-1);return;
    }
    core=sqlite3_value_int(argv[0]);
    rc=api->xColumnSize(fts,-1,&dl);
    if(rc!=SQLITE_OK){sqlite3_result_error_code(ctx,rc);return;}
    if(core<1||core>dl||api->xPhraseSize(fts,0)>8){
        sqlite3_result_error(ctx,"invalid core or phrase exceeds 8 tokens",-1);return;
    }
    rc=api->xInstCount(fts,&n);
    if(rc!=SQLITE_OK){sqlite3_result_error_code(ctx,rc);return;}
    for(i=0;i<n;++i){
        rc=api->xInst(fts,i,&phrase,&col,&off);
        if(rc!=SQLITE_OK){sqlite3_result_error_code(ctx,rc);return;}
        if(phrase!=0||col!=0||off<0){sqlite3_result_error(ctx,"invalid phrase instance",-1);return;}
        if(off<core)++count;
    }
    sqlite3_result_int(ctx,count);
}

/* Count only phrase occurrences that cross the split, never internal hits. */
static void crossing_count(const Fts5ExtensionApi *api,Fts5Context *fts,
                          sqlite3_context *ctx,int argc,sqlite3_value **argv){
    int rc,n=0,i,phrase,col,off,split,dl=0,plen,count=0;
    if(argc!=1||api->xPhraseCount(fts)!=1||api->xColumnCount(fts)!=1){
        sqlite3_result_error(ctx,"expected one phrase and split",-1);return;
    }
    split=sqlite3_value_int(argv[0]);plen=api->xPhraseSize(fts,0);
    rc=api->xColumnSize(fts,-1,&dl);
    if(rc!=SQLITE_OK){sqlite3_result_error_code(ctx,rc);return;}
    if(split<1||split>=dl||plen<1||plen>8){
        sqlite3_result_error(ctx,"invalid split or phrase",-1);return;
    }
    rc=api->xInstCount(fts,&n);
    if(rc!=SQLITE_OK){sqlite3_result_error_code(ctx,rc);return;}
    for(i=0;i<n;i++){
        rc=api->xInst(fts,i,&phrase,&col,&off);
        if(rc!=SQLITE_OK){sqlite3_result_error_code(ctx,rc);return;}
        if(phrase!=0||col!=0||off<0){sqlite3_result_error(ctx,"invalid instance",-1);return;}
        if(off<split&&off+plen>split)count++;
    }
    sqlite3_result_int(ctx,count);
}

typedef struct TokenCounter {
    fts5_tokenizer tok;
    Fts5Tokenizer *instance;
} TokenCounter;
static int token_cb(void *ctx,int flags,const char *text,int n,int start,int end){
    sqlite3_int64 *count=(sqlite3_int64*)ctx;
    (void)text;(void)n;(void)start;(void)end;
    if(!(flags & FTS5_TOKEN_COLOCATED)) ++*count;
    return SQLITE_OK;
}
static void count_tokens(sqlite3_context *ctx,int argc,sqlite3_value **argv){
    TokenCounter *tc=(TokenCounter*)sqlite3_user_data(ctx);
    sqlite3_int64 count=0;
    int rc,n;
    const unsigned char *s;
    if(argc!=1 || sqlite3_value_type(argv[0])!=SQLITE_TEXT){
        sqlite3_result_error(ctx,"expected UTF8 text",-1);return;
    }
    s=sqlite3_value_text(argv[0]); n=sqlite3_value_bytes(argv[0]);
    if(!s){sqlite3_result_error_nomem(ctx);return;}
    rc=tc->tok.xTokenize(tc->instance,&count,FTS5_TOKENIZE_DOCUMENT,(const char*)s,n,token_cb);
    if(rc!=SQLITE_OK){sqlite3_result_error_code(ctx,rc);return;}
    sqlite3_result_int64(ctx,count);
}
/* Exact length-prefixed sequence of default unicode61 document tokens.
 * No offset bytes, no lossy normalization outside the native tokenizer.
 * Fail closed if a tokenizer emits colocated synonyms. */
static int stream_cb(void *ctx,int flags,const char *text,int n,int start,int end){
    sqlite3_str *s=(sqlite3_str*)ctx;
    unsigned int u=(unsigned int)n;
    unsigned char len[4]={(unsigned char)(u>>24),(unsigned char)(u>>16),
                          (unsigned char)(u>>8),(unsigned char)u};
    (void)start;(void)end;
    if((flags & FTS5_TOKEN_COLOCATED)||n<=0)return SQLITE_ERROR;
    sqlite3_str_append(s,(const char*)len,4);
    sqlite3_str_append(s,text,n);
    return sqlite3_str_errcode(s);
}
static void token_stream(sqlite3_context *ctx,int argc,sqlite3_value **argv){
    TokenCounter *tc=(TokenCounter*)sqlite3_user_data(ctx);
    int rc,n,size;char *out;
    const unsigned char *text;
    sqlite3_str *s;
    if(argc!=1 || sqlite3_value_type(argv[0])!=SQLITE_TEXT){
        sqlite3_result_error(ctx,"expected UTF8 text",-1);return;
    }
    text=sqlite3_value_text(argv[0]);n=sqlite3_value_bytes(argv[0]);
    if(!text){sqlite3_result_error_nomem(ctx);return;}
    s=sqlite3_str_new(sqlite3_context_db_handle(ctx));
    rc=tc->tok.xTokenize(tc->instance,s,FTS5_TOKENIZE_DOCUMENT,(const char*)text,n,stream_cb);
    if(rc==SQLITE_OK)rc=sqlite3_str_errcode(s);
    size=sqlite3_str_length(s);out=sqlite3_str_finish(s);
    if(rc!=SQLITE_OK){sqlite3_free(out);sqlite3_result_error_code(ctx,rc);return;}
    if(size==0){sqlite3_free(out);sqlite3_result_zeroblob(ctx,0);return;}
    if(!out){sqlite3_result_error_nomem(ctx);return;}
    sqlite3_result_blob(ctx,out,size,sqlite3_free);
}

static void destroy_counter(void *ptr){
    TokenCounter *tc=(TokenCounter*)ptr;
    if(tc){if(tc->instance)tc->tok.xDelete(tc->instance);sqlite3_free(tc);}
}

#ifdef _WIN32
__declspec(dllexport)
#endif
int sqlite3_cdgfts_init(sqlite3 *db,char **err,const sqlite3_api_routines *api){
    sqlite3_stmt *st=0;
    fts5_api *fts=0;
    TokenCounter *tc=0;
    void *context=0;
    int rc;
    SQLITE_EXTENSION_INIT2(api);
    rc=sqlite3_prepare_v2(db,"SELECT fts5(?1)",-1,&st,0);
    if(rc==SQLITE_OK)rc=sqlite3_bind_pointer(st,1,&fts,"fts5_api_ptr",0);
    if(rc==SQLITE_OK){int step=sqlite3_step(st);if(step!=SQLITE_ROW)rc=step;}
    sqlite3_finalize(st);
    if(rc!=SQLITE_OK || !fts){*err=sqlite3_mprintf("FTS5 public API unavailable");return SQLITE_ERROR;}
    rc=fts->xCreateFunction(fts,"cdg_count",0,phrase_count,0);
    if(rc!=SQLITE_OK)return rc;
    rc=fts->xCreateFunction(fts,"cdg_length",0,row_length,0);
    if(rc!=SQLITE_OK)return rc;
    rc=fts->xCreateFunction(fts,"cdg_owned_count",0,owned_count,0);
    if(rc!=SQLITE_OK)return rc;
    rc=fts->xCreateFunction(fts,"cdg_crossing_count",0,crossing_count,0);
    if(rc!=SQLITE_OK)return rc;
    tc=sqlite3_malloc(sizeof(*tc));
    if(!tc)return SQLITE_NOMEM;
    tc->instance=0;
    rc=fts->xFindTokenizer(fts,"unicode61",&context,&tc->tok);
    if(rc==SQLITE_OK)rc=tc->tok.xCreate(context,0,0,&tc->instance);
    if(rc!=SQLITE_OK){destroy_counter(tc);return rc;}
    rc=sqlite3_create_function_v2(db,"cdg_token_count",1,SQLITE_UTF8|SQLITE_DETERMINISTIC,
                  tc,count_tokens,0,0,destroy_counter);
    if(rc!=SQLITE_OK)return rc;
    /* Both scalar functions are connection-local; token_count owns tc. */
    return sqlite3_create_function_v2(db,"cdg_token_stream",1,SQLITE_UTF8|SQLITE_DETERMINISTIC,
                  tc,token_stream,0,0,0);
}
