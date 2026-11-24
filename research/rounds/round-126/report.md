# R126: Direct fragment phrase counts and exact first-boundary correction

Status: pending original-source CI.

R125 reconstructs all active term positions to compute phrase frequency,
including common terms. For exact phrases of 1–3 canonical tokens, divide
occurrences into within-fragment and boundary-crossing starts. Assign a
crossing occurrence to the first boundary after its start; the left context
is limited to the owning fragment (last two tokens), while the right context
may span several short fragments. No double counting for multi-boundary or
overlapping repeated-token phrases. Aggregate native fragment phrase counts
through active applications. Compare a direct join, materialized fragment
match CTE with grouping, and reusable indexed boundary windows versus a
sparse exact crossing-bigram/trigram table. The window auxiliary uses the
public FTS5 xInst API and only counts matches starting before and ending
after the designated cut. Coalesce multiplicity intervals. Retain the
entire R125 min64_coalesced positional index and placements in both auxiliary
variants, charge all physical bytes. Independently check every original
version's complete bigram/trigram frequency decomposition, all persisted
boundary contexts/intervals and sampled phrase counts against native active
FTS5. Reuse R124/125 query plan and add first-prefix crossing-specific
queries. Same corpus and synthetic order, warm randomized rank-only timing,
no arbitrary FTS grammar, phrase length >3, source payload or WAL. Established
fragment reuse and boundary correction, not a novel algorithm claim.
