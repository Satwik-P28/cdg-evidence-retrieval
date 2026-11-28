"""R181: query-independent rejection so unseen phrases stop costing source reads.

R174 chose terms to give positions to, using queries from one corpus.  That policy
cannot help a phrase it never saw: 22 selected terms covered the training workload and
almost nothing else.  This round asks the complementary question -- is there a
*query-independent* structure that rejects candidates for any phrase, including phrases
that did not exist when the index was built?

Structures implemented (all charged by measured physical bytes):

``pairs``          exact adjacent-token pair postings: for every (a,b) that occurs
                   anywhere, the sorted set of content ids containing it.  A phrase can
                   only match a document that contains every one of its adjacent pairs,
                   so intersecting with these postings removes candidates and can never
                   remove a true match.
``pairs_selective``  the same, restricted to the pairs with the best document-frequency
                   per byte, to a physical byte budget.
``fingerprints``   one 64-bit bitmask per document over hashed adjacent pairs.  A clear
                   bit proves the pair is absent, so it rejects without false negatives.
                   Tight, cheap and approximate -- set bits prove nothing.
``positions``      the R174-style selective positional blocks, as the matched control.

The rule for every approximate structure here: a filter may only *reject*; it may never
supply a term frequency, and it is always followed by exact verification against the
source or against exact positions.  Corruption is detected, never tolerated: a damaged
posting list raises instead of silently dropping candidates.

Correctness is asserted per query, not per round: every ranking must equal the native
FTS5 oracle, which is only possible if no true match was filtered away.
"""
import argparse
import collections
import hashlib
import itertools
import json
import random
import shutil
import struct
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
for _p in ("round-158", "round-157", "round-173", "round-174", "round-175", "round-180",
           "round-165", "round-152", "round-141", "round-138", "round-136", "round-120"):
    sys.path.insert(0, str(HERE.parent / _p))

import zstandard as zstd  # noqa: E402
import forward_index as f  # noqa: E402
import token_tape as tt  # noqa: E402
from forward_index import h, ar, tokens, phrase_count  # noqa: E402
from blocked_positions import BlockIndex, rank_blocked, quant_us, tokens as bp_tokens  # noqa: E402
import cost_selection as cs  # noqa: E402
import workload as wl  # noqa: E402

EXTENSION = None
ZSTD = zstd.ZstdCompressor(level=9)
DZSTD = zstd.ZstdDecompressor()


# ---------------------------------------------------------------- primitives


def varint_bytes(values):
    out = bytearray()
    for v in values:
        while True:
            b = v & 0x7F
            v >>= 7
            if v:
                out.append(b | 0x80)
            else:
                out.append(b)
                break
    return bytes(out)


def read_varints(raw, count):
    out = []
    n = shift = 0
    for b in raw:
        n |= (b & 0x7F) << shift
        if b < 0x80:
            out.append(n)
            n = shift = 0
        else:
            shift += 7
            if shift > 63:
                raise ValueError("varint overflow in pair postings")
    if n or shift:
        raise ValueError("truncated pair postings")
    if len(out) != count:
        raise ValueError("pair posting count mismatch: %d != %d" % (len(out), count))
    return out


def pair_key(a, b):
    """Stable 64-bit identity for an ordered token pair.

    A hash collision can only merge two posting lists, which can only *add* candidates,
    and every candidate is verified exactly afterwards, so collisions cannot cause a
    false negative.
    """
    raw = int.from_bytes(hashlib.blake2b(a.encode() + b"\x00" + b.encode(), digest_size=8).digest(), "big")
    return raw & ((1 << 63) - 1)  # SQLite INTEGER is signed 64-bit


def doc_token_streams(db, tokdb):
    """Yield (content id, token stream) for every distinct stored content.

    The archive is content addressed: identical revisions share one content id, and the
    frequency index reports *content* ids.  Rejection structures must use the same
    identifier space, or rejecting a candidate would be based on another document's
    postings.  ``revisions`` maps generation to content id.
    """
    for cid, g in db.execute("SELECT cid, min(g) FROM revisions GROUP BY cid ORDER BY cid"):
        raw, _, _ = f.recover(db, g)
        yield cid, [t.decode("utf-8") if isinstance(t, bytes) else t
                    for t in bp_tokens(tokdb, raw.decode("utf-8"))]


# ---------------------------------------------------------------- builders


def build_pair_postings(db, tokdb, min_df=1, selective=False):
    """Adjacent-pair postings, delta-varint with a per-row dictionary entry.

    ``selective`` records that a later pruning step may remove postings.  It changes
    the meaning of a missing row: in a complete index a missing pair means the pair
    occurs nowhere, so every candidate can be rejected; in a selective index it only
    means the pair was not worth storing, so it must provide no information at all.
    Treating the two the same is exactly how a filter becomes unsound.
    """
    t0 = time.perf_counter()
    db.execute("CREATE TABLE pair_index_meta(selective INTEGER NOT NULL)")
    db.execute("INSERT INTO pair_index_meta VALUES(?)", (1 if selective else 0,))
    pairs = collections.defaultdict(list)
    endpoints = {}
    for cid, stream in doc_token_streams(db, tokdb):
        seen = set()
        for a, b in zip(stream, stream[1:]):
            k = pair_key(a, b)
            endpoints.setdefault(k, (a, b))
            if k not in seen:
                seen.add(k)
                pairs[k].append(cid)
    db.execute("CREATE TABLE pair_postings(pid INTEGER PRIMARY KEY, df INTEGER NOT NULL, body BLOB NOT NULL)")
    rows = []
    payload = 0
    for pid, cids in pairs.items():
        if len(cids) < min_df:
            continue
        cids.sort()
        deltas = varint_bytes([cids[0]] + [c - p for p, c in zip(cids, cids[1:])])
        body = ZSTD.compress(deltas) if len(deltas) > 64 else deltas
        payload += len(body)
        rows.append((pid, len(cids), body))
    db.executemany("INSERT INTO pair_postings VALUES(?,?,?)", rows)
    db.commit()
    sizes = dict(db.execute("SELECT name,sum(pgsize) FROM dbstat WHERE name='pair_postings' GROUP BY name"))
    endpoints = {pid: endpoints[pid] for pid, _, _ in rows}
    return dict(pair_count=len(rows), pair_payload_bytes=payload,
                pair_table_bytes=sizes.get("pair_postings", 0),
                pair_build_seconds=round(time.perf_counter() - t0, 3)), endpoints


def build_fingerprints(db, tokdb, bits=64):
    """One bitmask per document over hashed adjacent pairs (Bloom-free, exact-negative)."""
    t0 = time.perf_counter()
    db.execute("CREATE TABLE doc_pair_bits(cid INTEGER PRIMARY KEY, mask BLOB NOT NULL)")
    width = bits // 8
    rows = []
    for cid, stream in doc_token_streams(db, tokdb):
        mask = bytearray(width)
        for a, b in zip(stream, stream[1:]):
            k = pair_key(a, b) % bits
            mask[k >> 3] |= 1 << (k & 7)
        rows.append((cid, bytes(mask)))
    db.executemany("INSERT INTO doc_pair_bits VALUES(?,?)", rows)
    db.commit()
    sizes = dict(db.execute("SELECT name,sum(pgsize) FROM dbstat WHERE name='doc_pair_bits' GROUP BY name"))
    return dict(documents=len(rows), fingerprint_bits=bits, fingerprint_bytes=width * len(rows),
                fingerprint_table_bytes=sizes.get("doc_pair_bits", 0),
                fingerprint_build_seconds=round(time.perf_counter() - t0, 3))


def select_pairs_vocabulary(db, budget, endpoints, ids):
    """Buy a *token* set, and keep every pair whose two endpoints are in it.

    Buying individual posting lists optimises for pairs that already appear in some
    query, which is the R174 failure in a new costume: a phrase nobody anticipated gets
    no benefit.  Buying vocabulary instead covers every pair among the selected tokens,
    so an unseen phrase built from common words is still filtered.

    Tokens enter in document-frequency order; a token is affordable when the pairs it
    completes with tokens already bought fit in the remaining budget.
    """
    if budget is None:
        return None
    sizes = {pid: (df, length) for pid, df, length in
             db.execute("SELECT pid,df,length(body) FROM pair_postings")}
    counts = dict(db.execute("SELECT tid,n FROM token_postings"))
    tokens = [(term.decode("utf-8") if isinstance(term, (bytes, bytearray)) else term,
               tid, counts.get(tid, 0)) for term, tid in ids.items()]
    incident = collections.defaultdict(list)
    for pid, (a, b) in endpoints.items():
        incident[a].append(pid)
        incident[b].append(pid)
    bought = set()
    keep = set()
    spent = 0.0
    for term, tid, df in sorted(tokens, key=lambda t: (-t[2], t[0])):
        completes = []
        for pid in incident.get(term, ()):
            a, b = endpoints[pid]
            other = b if a == term else a
            if other == term or other not in bought:
                continue
            completes.append(pid)
        cost = sum(sizes[pid][1] + 24 for pid in completes)
        if spent + cost > budget:
            continue
        bought.add(term)
        keep.update(completes)
        spent += cost
    return keep


def select_pairs(db, budget, documents=None):
    """Keep the pairs with the most *rejection* per stored byte.

    A pair that occurs in most documents rejects almost nothing; a pair that occurs in a
    handful rejects almost every candidate for any phrase containing it.  So the value of
    a posting list is ``(1 - df/N)`` -- the fraction of documents it can rule out -- and
    the selection maximises that value per byte.  Ranking by document frequency itself is
    the opposite rule and buys expensive lists that filter almost nothing.
    """
    if budget is None:
        return None
    rows = db.execute("SELECT pid,df,length(body) FROM pair_postings ORDER BY pid").fetchall()
    if documents is None:
        documents = db.execute("SELECT count(DISTINCT cid) FROM revisions").fetchone()[0] or 1
    def value(row):
        pid, df, size = row
        return (1.0 - df / max(1, documents)) / max(1.0, size + 24.0)
    ranked = sorted(rows, key=lambda r: (-value(r), r[1], r[0]))
    keep = set()
    spent = 0
    for pid, df, size in ranked:
        cost = size + 24
        if spent + cost > budget:
            continue
        keep.add(pid)
        spent += cost
    return keep


# ---------------------------------------------------------------- query time


class Filters:
    """Candidate rejection structures for one archive, with per-query counters."""

    def __init__(self, db):
        self.db = db
        self.pair_cache = {}
        self.bits = None
        self.work = collections.Counter()
        self.selective = self._selective()

    def _selective(self):
        row = self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='pair_index_meta'").fetchone()
        if row is None:
            return False
        return bool(self.db.execute("SELECT selective FROM pair_index_meta").fetchone()[0])

    def has_pairs(self):
        return self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='pair_postings'").fetchone() is not None

    def has_bits(self):
        return self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='doc_pair_bits'").fetchone() is not None

    def pair_set(self, a, b):
        k = pair_key(a, b)
        if k in self.pair_cache:
            return self.pair_cache[k]
        row = self.db.execute("SELECT df,body FROM pair_postings WHERE pid=?", (k,)).fetchone()
        if row is None:
            out = None
        else:
            df, body = row
            try:
                raw = DZSTD.decompress(body) if self._compressed(body) else body
            except zstd.ZstdError as exc:
                raise ValueError("corrupt pair postings for %s %s" % (a, b)) from exc
            # Stored as first-id plus deltas: the decoder must re-accumulate, or it
            # returns gaps and rejects documents that really contain the pair.
            out = set(itertools.accumulate(read_varints(raw, df)))
            self.work["pair_bytes_activated"] += len(body)
            self.work["pairs_activated"] += 1
        self.pair_cache[k] = out
        return out

    @staticmethod
    def _compressed(body):
        return body[:4] == b"\x28\xb5\x2f\xfd"  # zstd frame magic

    def mask(self, cid):
        if self.bits is None:
            self.bits = {}
        if cid not in self.bits:
            row = self.db.execute("SELECT mask FROM doc_pair_bits WHERE cid=?", (cid,)).fetchone()
            if row is None:
                raise ValueError("missing fingerprint for document %d" % cid)
            self.bits[cid] = row[0]
            self.work["fingerprint_bytes_activated"] += len(row[0])
        return self.bits[cid]

    def reject(self, stream, candidates):
        """Remove candidates that cannot contain the phrase at all."""
        before = len(candidates)
        if self.has_pairs():
            for a, b in zip(stream, stream[1:]):
                posting = self.pair_set(a, b)
                if posting is None:
                    if self.selective:
                        # Not stored, so it says nothing about this candidate.
                        self.work["pairs_unindexed"] += 1
                        continue
                    # A complete index knows this pair occurs nowhere.
                    candidates = set()
                    break
                candidates = {c for c in candidates if c in posting}
                if not candidates:
                    break
        if self.has_bits() and candidates:
            width = 8
            for a, b in zip(stream, stream[1:]):
                k = pair_key(a, b) % 64
                keep = set()
                for c in candidates:
                    mask = self.mask(c)
                    if len(mask) != width:
                        raise ValueError("corrupt document fingerprint")
                    if mask[k >> 3] & (1 << (k & 7)):
                        keep.add(c)
                candidates = keep
                if not candidates:
                    break
        self.work["candidates_before_filter"] += before
        self.work["candidates_after_filter"] += len(candidates)
        self.work["candidates_rejected"] += before - len(candidates)
        return candidates


def rank_filtered(db, p, o, prep, index, filters):
    """Exact historical BM25; rejection narrows candidates, verification stays exact."""
    ar.expression(p, o)
    active, lens, n, total = prep
    index.reset()
    freq = []
    for phrase in p:
        qs = tokens(db, phrase)
        qids = [index.ids.get(t) for t in qs]
        if None in qids:
            freq.append({})
            continue
        if len(qids) == 1:
            matches = {cid: tf for cid, tf in index.all_counts(qids[0]).items() if cid in active}
        else:
            maps = [index.all_counts(t) for t in qids]
            candidates = {cid for cid in set.intersection(*(set(m) for m in maps)) if cid in active}
            index.work["candidate_checks"] += len(candidates)
            text = [q.decode("utf-8") if isinstance(q, (bytes, bytearray)) else str(q) for q in qs]
            candidates = filters.reject(text, candidates)
            matches = {}
            cache = {}
            for cid in candidates:
                if cid not in cache:
                    raw, dd, ab = f.recover(db, cid)
                    cache[cid] = (b" ".join(tokens(db, raw.decode("utf8"))), ab, dd)
                    index.work["source_reads"] += 1
                    index.work["source_decoded_bytes"] += dd
                    index.work["source_activated_bytes"] += ab
                tf = phrase_count(cache[cid][0], qs)
                if tf:
                    matches[cid] = tf
                index.work["source_resolved"] += 1
        expanded = {g: tf for cid, tf in matches.items() for g in active[cid]}
        if any(not 1 <= tf <= lens[g] for g, tf in expanded.items()):
            raise ValueError("frequency bound")
        freq.append(expanded)
    hits, df = ar.score(freq, o, n, total, lens)
    return hits, df, index.work, filters.work


# ---------------------------------------------------------------- archive assembly


def make_archive(base, path, extra):
    shutil.copyfile(base, path)
    db = f.connect(path, EXTENSION)
    for table in extra:
        db.execute("DROP TABLE IF EXISTS %s" % table)
    db.close()
    return f.connect(path, EXTENSION)


def arm_specs(pct_pairs, pct_positions):
    return {
        "freq": dict(pairs=None, bits=None, positions=False, budget=None),
        "pairs_all": dict(pairs="all", bits=None, positions=False, budget=None),
        "pairs_selective-%d%%" % pct_pairs: dict(pairs=pct_pairs, bits=None, positions=False, budget=pct_pairs),
        "fingerprints64": dict(pairs=None, bits=64, positions=False, budget=None),
        "positions-%d%%" % pct_positions: dict(pairs=None, bits=None, positions=True, budget=pct_positions),
        "pairs_all+positions-%d%%" % pct_positions: dict(pairs="all", bits=None, positions=True,
                                                         budget=pct_positions),
    }


def evaluate(db, ids, plan_by_cut, expected, index, filters):
    times = []
    work = collections.Counter()
    filter_work = collections.Counter()
    err = 0.0
    mismatches = []
    tie_only = 0
    order = list(plan_by_cut)
    random.Random(181).shuffle(order)
    preps = {}
    for cut, p, o in order:
        if cut not in preps:
            preps[cut] = f.prepare(db, cut)
        t = time.perf_counter_ns()
        hits, df, w, fw = rank_filtered(db, p, o, preps[cut], index, filters)
        times.append((time.perf_counter_ns() - t) / 1000)
        work.update(w)
        filter_work.update(fw)
        want = expected[cut, p, o]
        try:
            err = max(err, h.verify(hits, want))
        except AssertionError:
            # Distinguish a real ranking error from a different order among documents
            # whose BM25 scores are equal to floating-point tolerance.  The oracle and
            # this scorer sum the same terms in a different order, so exact ties can
            # sort differently; anything beyond tolerance is a genuine defect.
            got_ids = [g for g, _ in hits]
            want_ids = [g for g, _ in want]
            got_scores = {g: s for g, s in hits}
            want_scores = {g: s for g, s in want}
            if sorted(got_ids) == sorted(want_ids):
                spread = max(abs(got_scores.get(g, 0.0) - want_scores.get(g, 0.0))
                             for g in set(got_ids) | set(want_ids))
                if spread <= 1e-6:
                    tie_only += 1
                    continue
            else:
                spread = None
            if len(mismatches) < 5:
                mismatches.append(dict(cut=cut, phrases=list(p), op=o, got=got_ids, want=want_ids,
                                       got_scores=[round(s, 9) for s in (got_scores.get(g, 0.0) for g in got_ids)],
                                       want_scores=[round(s, 9) for s in (want_scores.get(g, 0.0) for g in want_ids)],
                                       score_spread=spread))
            err = max(err, 1.0)
    return dict(query=quant_us(times), work=dict(work), filter_work=dict(filter_work),
                rank_checks=len(times), score_error=err,
                tie_order_differences=tie_only, rank_mismatches=mismatches)


def run(a):
    global EXTENSION
    EXTENSION = a.extension.resolve()
    corpus = a.corpus
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        if corpus == "clark":
            import clark_retrieval as cr
            events, _, m, _, _ = cr.read(a.source)
            manifest = h.sha(h.canonical(m)).hex()
            if manifest != wl.EXPECTED["clark"]:
                raise ValueError("CLARK manifest")
            n = len(events)
            cuts = [n // 4, n // 2, 3 * n // 4, n]
            wpath = HERE.parent / "round-180" / "manifest-clark-1161.json"
        else:
            from frequency_index import nr
            events, _, m = nr.load(a.source, a.target, folder)
            manifest = m["source_manifest_sha256"]
            if manifest != wl.EXPECTED["ap"]:
                raise ValueError("AP manifest")
            n = len(events)
            first = len(m["retained_paths"])
            cuts = [first, first + (n - first) // 3, first + 2 * (n - first) // 3, n]
            wpath = HERE.parent / "round-180" / "manifest-ap-10009.json" if a.target == 10000 else None
        frozen = json.loads(wpath.read_text())
        templates = frozen["templates"]
        digest = frozen["manifest"]["workload_sha256"]

        refs = {c: h.active_oracle(events, c) for c in cuts}
        expected = {}
        plan_by_cut = []
        for t in templates:
            cut = t["eval_cut"]
            p = tuple(" ".join(ph) for ph in t["phrases"])
            o = t["op"]
            key = (cut, p, o)
            if key not in expected:
                expected[key] = h.native(refs[cut], p, o)
            plan_by_cut.append((cut, p, o))
        for ref in refs.values():
            ref.close()

        specs = arm_specs(a.pairs_pct, a.positions_pct)
        base = folder / "base.sqlite"
        db, base_size = f.build(base, EXTENSION, events, "marginal", False)
        # R174's extractor reads positions from the freshly built FTS table, so it has
        # to run before the frequency tape replaces it (same order as R174).
        terms = cs.extract(db) if any(s["positions"] for s in specs.values()) else {}
        base_size.update(tt.build_tape(db, base, events, "frequency"))
        ids, _ = tt.vocabulary(db)
        db.close()
        base_bytes = base.stat().st_size

        tokdb = f.connect(":memory:", EXTENSION)
        pair_db = make_archive(base, folder / "pairs.sqlite", [])
        pair_meta, endpoints = build_pair_postings(pair_db, tokdb, min_df=1)
        pair_db.commit()
        pair_db.execute("VACUUM")
        pair_db.close()

        fp_db = make_archive(base, folder / "fp.sqlite", [])
        fp_meta = build_fingerprints(fp_db, tokdb, bits=64)
        fp_db.commit()
        fp_db.execute("VACUUM")
        fp_db.close()

        out = {}
        for name, spec in specs.items():
            if a.only and name not in a.only:
                continue
            path = folder / (name.replace("+", "_").replace("%", "pct") + ".sqlite")
            if spec["pairs"] == "all":
                shutil.copyfile(folder / "pairs.sqlite", path)
                extra = pair_meta
            elif isinstance(spec["pairs"], int):
                shutil.copyfile(folder / "pairs.sqlite", path)
                dbx = f.connect(path, EXTENSION)
                dbx.execute("UPDATE pair_index_meta SET selective=1")
                keep = select_pairs_vocabulary(dbx, spec["budget"] / 100.0 * base_bytes,
                                               endpoints, ids)
                dbx.execute("CREATE TABLE kept(pid INTEGER PRIMARY KEY)")
                dbx.executemany("INSERT INTO kept VALUES(?)", ((p,) for p in sorted(keep)))
                dbx.execute("DELETE FROM pair_postings WHERE pid NOT IN (SELECT pid FROM kept)")
                dbx.execute("DROP TABLE kept")
                dbx.commit()
                dbx.execute("VACUUM")
                dbx.close()
                extra = dict(selected_pairs=len(keep))
            elif spec["bits"]:
                shutil.copyfile(folder / "fp.sqlite", path)
                extra = fp_meta
            else:
                shutil.copyfile(base, path)
                extra = {}
            dbx = f.connect(path, EXTENSION)
            if spec["positions"]:
                budget = spec["budget"] / 100.0 * base_bytes
                rows = cs.score_terms(terms, ids, "df", {}) if terms else []
                chosen, spent = cs.greedy(rows, budget)
                dbx.execute("CREATE TABLE term_blocks(tid INTEGER PRIMARY KEY,n_postings INTEGER NOT NULL,"
                            "nblocks INTEGER NOT NULL,dir BLOB NOT NULL,body BLOB NOT NULL)")
                by_tid = {ids[t]: (s, e) for t, (s, e) in terms.items()}
                for tid in chosen:
                    stats, enc = by_tid[tid]
                    dbx.execute("INSERT INTO term_blocks VALUES(?,?,?,?,?)",
                                (tid, stats["df"], enc["blocks"], enc["dir"], enc["body"]))
                dbx.commit()
                dbx.execute("VACUUM")
                extra.update(selected_terms=len(chosen), selection_bytes=spent)
            sizes = dict(dbx.execute("SELECT name,sum(pgsize) FROM dbstat GROUP BY name"))
            index = BlockIndex(dbx, ids, True)
            filters = Filters(dbx)
            stats = evaluate(dbx, ids, plan_by_cut, expected, index, filters)
            dbx.close()
            out[name] = dict(**{k: v for k, v in spec.items() if k != "budget"},
                             budget_pct=spec["budget"], **extra, **stats,
                             sqlite_bytes=path.stat().st_size,
                             table_bytes=sizes,
                             budget_fraction=path.stat().st_size / base_bytes,
                             base_archive_bytes=base_bytes)
            print("ARM_JSON=" + json.dumps(dict(
                name=name, sqlite=out[name]["sqlite_bytes"],
                median=stats["query"]["median_us"], p95=stats["query"]["p95_us"],
                p99=stats["query"]["p99_us"], max=stats["query"]["max_us"],
                src=stats["work"].get("source_reads"),
                rejected=stats["filter_work"].get("candidates_rejected"),
                before=stats["filter_work"].get("candidates_before_filter")), default=str), flush=True)
        tokdb.close()
        result = dict(round=181, corpus=corpus, revisions=len(events), manifest_sha256=manifest,
                      cutoffs=cuts, workload_sha256=digest, workload_source=str(wpath.name),
                      query_count=len(plan_by_cut), base_archive_bytes=base_bytes,
                      pair_metadata=pair_meta, fingerprint_metadata=fp_meta, arms=out,
                      limitations=[
                          "logical activation of stored bytes; no physical page I/O",
                          "pair identity is a 64-bit content hash; collisions can only add candidates, "
                          "which are verified exactly afterwards",
                          "fingerprints are 64 bits per document, so false positives are common and "
                          "expected; they can only reject on a clear bit",
                          "corrupted postings raise instead of returning a short candidate list",
                          "warm-cache timing; every ranking is compared with the native FTS5 oracle"])
        if a.out.exists():
            old = json.loads(a.out.read_text())
            if old.get("manifest_sha256") == manifest and old.get("workload_sha256") == digest:
                old["arms"].update(result["arms"])
                result = old
        a.out.write_text(json.dumps(result, indent=2, default=str) + "\n")
        print("RESULT_JSON=" + json.dumps(dict(round=181, corpus=corpus, arms=len(result["arms"]),
                                              workload=digest)))


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--corpus", choices=("ap", "clark"), required=True)
    p.add_argument("--target", type=int, default=10000)
    p.add_argument("--extension", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--only", default="")
    p.add_argument("--pairs-pct", type=int, default=5)
    p.add_argument("--positions-pct", type=int, default=5)
    return p.parse_args()


if __name__ == "__main__":
    a = parse_args()
    a.only = {x for x in a.only.split(",") if x}
    run(a)
