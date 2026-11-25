import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.io.*;
import java.security.MessageDigest;
import org.apache.lucene.analysis.*;
import org.apache.lucene.analysis.standard.StandardAnalyzer;
import org.apache.lucene.analysis.tokenattributes.CharTermAttribute;
import org.apache.lucene.document.*;
import org.apache.lucene.index.*;
import org.apache.lucene.search.*;
import org.apache.lucene.search.similarities.BM25Similarity;
import org.apache.lucene.store.*;
import org.apache.lucene.util.SmallFloat;

public class NativeReference {
    static class Rev {
        int g; String name,text; Map<String,Integer> tf=new TreeMap<>(); int length;
        Rev(String row, Analyzer analyzer) throws Exception {
            String[] f=row.split("\\t",-1); g=Integer.parseInt(f[0]);
            name=new String(Base64.getDecoder().decode(f[1]),StandardCharsets.UTF_8);
            text=new String(Base64.getDecoder().decode(f[2]),StandardCharsets.UTF_8);
            try(TokenStream ts=analyzer.tokenStream("content",text)){
                CharTermAttribute term=ts.addAttribute(CharTermAttribute.class);
                ts.reset();while(ts.incrementToken()){tf.merge(term.toString(),1,Integer::sum);length++;}ts.end();
            }
        }
    }
    static TreeMap<String,Rev> active(List<Rev> all,int cutoff) {
        TreeMap<String,Rev> out=new TreeMap<>();
        for(Rev r:all){if(r.g>cutoff)break;out.put(r.name,r);}
        return out;
    }
    static String enc(String x){return Base64.getEncoder().encodeToString(x.getBytes(StandardCharsets.UTF_8));}
    static String hash(String t){
        try{return Base64.getEncoder().encodeToString(MessageDigest.getInstance("SHA-256").digest(("CDG-R140-v1|"+t).getBytes(StandardCharsets.UTF_8)));}
        catch(Exception e){throw new RuntimeException(e);}
    }
    public static void main(String[] args) throws Exception {
        Path events=Paths.get(args[0]),out=Paths.get(args[1]);Files.createDirectories(out);
        int[] cuts=Arrays.stream(args[2].split(",")).mapToInt(Integer::parseInt).toArray();
        try(Analyzer analyzer=new StandardAnalyzer()){
            List<Rev> all=new ArrayList<>();
            for(String row:Files.readAllLines(events,StandardCharsets.UTF_8))all.add(new Rev(row,analyzer));
            Map<String,Integer> df=new HashMap<>();
            for(Rev r:active(all,cuts[0]).values())for(String t:r.tf.keySet())if(t.matches("[a-z]{3,30}"))df.merge(t,1,Integer::sum);
            List<String> queries=new ArrayList<>();
            for(int[] band:new int[][]{{1,2},{3,10},{11,Integer.MAX_VALUE}}){
                df.keySet().stream().filter(t->df.get(t)>=band[0]&&df.get(t)<=band[1])
                    .sorted(Comparator.comparing(NativeReference::hash).thenComparing(t->t)).limit(24).forEach(queries::add);
            }
            if(queries.isEmpty())throw new IllegalStateException("empty query plan");
            Files.write(out.resolve("queries.txt"),queries,StandardCharsets.UTF_8);
            Map<String,Integer> next=new HashMap<>();Map<Integer,Integer> ends=new HashMap<>();
            for(int i=all.size()-1;i>=0;i--){Rev r=all.get(i);ends.put(r.g,next.getOrDefault(r.name,0));next.put(r.name,r.g);}
            try(PrintWriter d=new PrintWriter(Files.newBufferedWriter(out.resolve("docs.tsv")));
                PrintWriter t=new PrintWriter(Files.newBufferedWriter(out.resolve("terms.tsv")))){
                for(Rev r:all){
                    int approx=SmallFloat.byte4ToInt(SmallFloat.intToByte4(r.length));
                    d.println(r.g+"\t"+enc(r.name)+"\t"+r.length+"\t"+approx+"\t"+ends.get(r.g));
                    for(Map.Entry<String,Integer> e:r.tf.entrySet())t.println(r.g+"\t"+enc(e.getKey())+"\t"+e.getValue());
                }
            }
            try(PrintWriter writer=new PrintWriter(Files.newBufferedWriter(out.resolve("native.tsv")))){
                for(int cut:cuts){
                    BM25Similarity sim=new BM25Similarity(1.2f,0.75f);sim.setDiscountOverlaps(false);
                    try(Directory dir=new ByteBuffersDirectory()){
                        IndexWriterConfig cfg=new IndexWriterConfig(analyzer);cfg.setSimilarity(sim);
                        try(IndexWriter iw=new IndexWriter(dir,cfg)){
                            for(Rev r:active(all,cut).values()){
                                Document doc=new Document();doc.add(new TextField("content",r.text,Field.Store.NO));
                                doc.add(new StoredField("name",r.name));iw.addDocument(doc);
                            }
                        }
                        try(DirectoryReader reader=DirectoryReader.open(dir)){
                            IndexSearcher searcher=new IndexSearcher(reader);searcher.setSimilarity(sim);
                            for(String query:queries){
                                TopDocs hits=searcher.search(new TermQuery(new Term("content",query)),10);
                                for(ScoreDoc hit:hits.scoreDocs)writer.println(cut+"\t"+query+"\t"+enc(searcher.doc(hit.doc).get("name"))+"\t"+Float.toString(hit.score));
                            }
                        }
                    }
                }
            }
        }
    }
}
