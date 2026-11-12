# Application-facing research description

## One-paragraph project description

I have been investigating a failure mode in retrieval systems: passages that individually look relevant may still omit information needed to support a claim. My current work studies evidence as sets of source-linked spans and explores when selecting complete sets is worth the additional retrieval and storage cost. I built lexical baselines, tested exact alignment of annotated SciFact rationales, modeled seekable source-frame layouts, and examined dependency-aware selection with controlled synthetic experiments. Some results were negative, particularly when BM25 already recovered nearly all required evidence. The main open problem is whether a non-oracle dependency model can improve source-grounded retrieval on difficult held-out queries without adding more overhead than it saves.

## What to say when asked about originality

The project is an exploratory systems research agenda, not a novel algorithm established by publication. The potential distinction is the coupling of evidence-set completeness, exact source receipts and physical access cost. Individually, these have extensive prior art, and the combined approach has not yet shown a non-dominated end-to-end result.

## What not to claim

- That the oracle 100% success from a synthetic control is real-world accuracy.
- That the full SciFact evaluation has been independently replicated locally.
- That exact source-quote alignment proves entailment or original byte identity.
- That compressed source I/O or RAG answer quality beats production systems.
- That all experimental code was independently authored without assistance if that is inaccurate.

## Interview questions worth being able to answer

1. Why is complete evidence-set recall different from top-k source recall?
2. When does BM25 already make dependency-aware retrieval unnecessary?
3. What exactly is an oracle lower bound, and why is it not a deployable gain?
4. What breaks when canonicalization changes source offsets?
5. How does a 512-byte physical frame differ from a 512-token prompt chunk?
6. What does a calibrated confidence estimate mean when source families shift?
7. Which experiment would make you abandon the graph controller?
