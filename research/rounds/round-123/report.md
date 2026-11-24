# R123: Native compact temporal access and physical layout ablation

Status: pending original-source CI.

Implement a wire-compatible C front-coded term lookup and selected-list
varint active-ordinal filter; compare identical direct/shared16 files with
Python and C access, then test eight fixed layouts (direct, shared4/16,
rowid versus WITHOUT ROWID, 8/16 KiB pages, hybrid 4/16 KiB groups that
isolate terms with at least 128 intervals). No query labels or frequency
training beyond posting cardinality. All layouts preserve R122 local
ordinal records and source-free metadata. Collect dbstat page accounting
when available. Exhaustively verify all persisted records; check native
counts for every vocabulary term at each of four cutoffs in direct/shared16
layouts, then independently rebuilt active-only FTS5 ranking for all
methods. Separate bounded decoded-block LRU experiment (0, 64, 256 KiB)
with identical synthetic repeated query stream and two-lookups on miss.
Budget excludes Python object overhead. No actual access history or I/O
claims. Same pinned Versions corpus; term-only, no positional parity.
Native C decoder not a new codec. Source payloads and update WAL excluded.
