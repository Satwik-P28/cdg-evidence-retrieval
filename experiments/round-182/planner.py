"""R182: a cost-aware execution planner over rejection, positions and raw sources.

R181 measured the representations separately.  This round asks the operational question:
given several of them in one archive, which should a query use?

The planner estimates, per phrase and before touching a source frame, the logical bytes
each execution mode would activate, and picks the cheapest:

``source``            frequency postings, then verify every candidate against its source
``positions``         exact positions for the phrase's tokens, no source read
``pairs_source``      reject with adjacent-pair postings, verify survivors from source
``pairs_positions``   reject with pairs, then use positions for the survivors

The estimate uses the features the brief names: candidate count, positional coverage,
estimated block activation from the term directories, source frame cost, expected decoded
bytes, phrase length, the active snapshot, and which rejection structures exist.

Constants come from the archive's own stored averages, never from the held-out workload.
Every plan is charged: the mode-choice lookups are counted, and the archive that holds all
the structures is reported at its measured physical size, not its estimated budget.

Nothing here may change an answer.  Every mode ends in exact verification, and every
ranking is compared with the native FTS5 oracle.
"""
import argparse
import collections
import json
import random
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
for _p in ("round-181", "round-180", "round-174", "round-173", "round-158", "round-157",
           "round-165", "round-152", "round-141", "round-138", "round-136", "round-120"):
    sys.path.insert(0, str(HERE.parent / _p))

import forward_index as f  # noqa: E402
import token_tape as tt  # noqa: E402
from forward_index import h, ar, tokens, phrase_count  # noqa: E402
from blocked_positions import BlockIndex, quant_us, shifted_count  # noqa: E402
import cost_selection as cs  # noqa: E402
import rejection as rj  # noqa: E402
import workload as wl  # noqa: E402

EXTENSION = None


class CostModel:
    """Byte-cost estimates from the archive's own measured averages."""

    def __init__(self, db, index, filters, mean_frame, rates=None):
        self.index = index
        self.filters = filters
        self.mean_frame = mean_frame
        # Calibrated on the training split only: microseconds per source read, per pair
        # posting byte and per activated position block.  None means "plan in bytes".
        self.rates = rates
        rows = db.execute("SELECT count(*), coalesce(sum(length(body)),0) FROM term_blocks").fetchone()
        self.position_rows, position_bytes = rows[0], rows[1]
        self.mean_position_bytes = (position_bytes / rows[0]) if rows[0] else 0.0
        pair = db.execute("SELECT count(*), coalesce(sum(length(body)),0) FROM pair_postings").fetchone()
        self.mean_pair_bytes = (pair[1] / pair[0]) if pair[0] else 0.0

    def plan(self, stream, qids, candidates, index, filters):
        """Return (mode, estimates).  The cheapest estimate wins."""
        n = max(1, len(candidates))
        covered = all(t is not None and index.directory(t) is not None for t in qids)
        estimates = {"source": n * self.mean_frame}
        if covered:
            # Only the blocks that can hold a candidate are decoded, so activation scales
            # with the candidate count rather than with the term's whole posting list.
            estimates["positions"] = n * max(8.0, self.mean_position_bytes * 0.25) * len(qids)
        if filters.has_pairs() and len(stream) >= 2:
            posting_bytes = 0
            smallest = n
            known = True
            for a, b in zip(stream, stream[1:]):
                row = filters.db.execute("SELECT df,length(body) FROM pair_postings WHERE pid=?",
                                         (rj.pair_key(a, b),)).fetchone()
                if row is None:
                    if filters.selective:
                        continue
                    known = False
                    smallest = 0
                    break
                posting_bytes += row[1]
                smallest = min(smallest, row[0])
            # A missing pair in a complete index means the phrase cannot occur at all.
            after = min(n, smallest) if known else 0
            estimates["pairs_source"] = posting_bytes + after * self.mean_frame
            if covered:
                estimates["pairs_positions"] = posting_bytes + after * max(
                    8.0, self.mean_position_bytes * 0.25) * len(qids)
        if self.rates:
            # Convert byte estimates into predicted microseconds with rates measured on
            # the training split, so the planner optimises the quantity a user feels.
            r = self.rates
            blocks = max(1.0, n * len(qids) * 0.25)
            timed = {"source": n * r["source_us"]}
            if covered:
                timed["positions"] = blocks * r["block_us"]
            if filters.has_pairs() and len(stream) >= 2:
                pair_bytes = 0
                after = n
                for a_tok, b_tok in zip(stream, stream[1:]):
                    row = filters.db.execute(
                        "SELECT df,length(body) FROM pair_postings WHERE pid=?",
                        (rj.pair_key(a_tok, b_tok),)).fetchone()
                    if row is None:
                        if filters.selective:
                            continue
                        after = 0
                        break
                    pair_bytes += row[1]
                    after = min(after, row[0])
                after = max(1.0, min(n, after))
                timed["pairs_source"] = pair_bytes * r["pair_byte_us"] + after * r["source_us"]
                if covered:
                    timed["pairs_positions"] = (pair_bytes * r["pair_byte_us"]
                                                + after * len(qids) * 0.25 * r["block_us"])
            estimates = timed
        mode = min(estimates, key=lambda k: (estimates[k], k))
        return mode, estimates


def _after_count(model, stream, filters, n):
    """Smallest indexed adjacent-pair document frequency: an upper bound on survivors."""
    smallest = n
    for a, b in zip(stream, stream[1:]):
        row = filters.db.execute("SELECT df FROM pair_postings WHERE pid=?",
                                 (rj.pair_key(a, b),)).fetchone()
        if row is None:
            if filters.selective:
                continue
            return 0
        smallest = min(smallest, row[0])
    return smallest


def rank_planned(db, p, o, prep, index, filters, model, strategy):
    """Execute one query.  ``strategy`` is a fixed mode, or ``planner`` to choose."""
    ar.expression(p, o)
    active, lens, n, total = prep
    index.reset()
    pair_base = dict(filters.work)
    chosen = collections.Counter()
    freq = []
    for phrase in p:
        qs = tokens(db, phrase)
        qids = [index.ids.get(t) for t in qs]
        if None in qids:
            freq.append({})
            continue
        stream = [q.decode("utf-8") if isinstance(q, (bytes, bytearray)) else str(q) for q in qs]
        if len(qids) == 1:
            matches = {cid: tf for cid, tf in index.all_counts(qids[0]).items() if cid in active}
        else:
            maps = [index.all_counts(t) for t in qids]
            candidates = {cid for cid in set.intersection(*(set(m) for m in maps)) if cid in active}
            index.work["candidate_checks"] += len(candidates)
            mode = strategy
            if strategy == "planner":
                mode, estimates = model.plan(stream, qids, candidates, index, filters)
                index.work["plan_lookups"] += len(estimates)
            chosen[mode] += 1
            if mode.startswith("pairs"):
                candidates = filters.reject(stream, candidates)
            matches = {}
            cache = {}
            use_positions = mode in ("positions", "pairs_positions")
            for cid in candidates:
                if use_positions:
                    lists = []
                    for i, t in zip(range(len(qids)), qids):
                        if index.directory(t) is None:
                            # No positions for this term: fall back to the source.
                            lists = None
                            break
                        k = index.block_of(t, cid)
                        if k is None:
                            lists = None
                            break
                        ps = index.block(t, k, True)["positions"].get(cid)
                        if ps is None:
                            lists = None
                            break
                        lists.append((i, ps))
                    if lists is not None:
                        upper = shifted_count(lists, lens[active[cid][0]], len(qids))
                        if upper:
                            matches[cid] = upper
                            index.work["position_exact"] += 1
                        else:
                            index.work["position_rejections"] += 1
                        continue
                if cid not in cache:
                    raw, dd, ab = f.recover(db, cid)
                    cache[cid] = b" ".join(tokens(db, raw.decode("utf8")))
                    index.work["source_reads"] += 1
                    index.work["source_decoded_bytes"] += dd
                    index.work["source_activated_bytes"] += ab
                tf = phrase_count(cache[cid], qs)
                if tf:
                    matches[cid] = tf
                index.work["source_resolved"] += 1
        expanded = {g: tf for cid, tf in matches.items() for g in active[cid]}
        if any(not 1 <= tf <= lens[g] for g, tf in expanded.items()):
            raise ValueError("frequency bound")
        freq.append(expanded)
    hits, df = ar.score(freq, o, n, total, lens)
    for k, v in chosen.items():
        index.work["mode_" + k] += v
    # Report only this query's filter work: filters.work is cumulative across the whole run,
    # so returning it whole would charge every arm for the work of the arms before it.
    delta = {k: filters.work.get(k, 0) - pair_base.get(k, 0) for k in filters.work}
    return hits, df, index.work, delta


def measure(db, queries, expected, index, filters, model, strategy):
    times = []
    work = collections.Counter()
    filter_work = collections.Counter()
    mismatches = []
    tie_only = 0
    samples = []
    preps = {}
    for cut, p, o in queries:
        if cut not in preps:
            preps[cut] = f.prepare(db, cut)
        t = time.perf_counter_ns()
        hits, df, w, fw = rank_planned(db, p, o, preps[cut], index, filters, model, strategy)
        elapsed = (time.perf_counter_ns() - t) / 1000
        times.append(elapsed)
        work.update(w)
        filter_work.update(fw)
        samples.append((elapsed, w.get("source_reads", 0), w.get("blocks_activated", 0),
                        fw.get("pair_bytes_activated", 0)))
        want = expected[cut, p, o]
        try:
            h.verify(hits, want)
        except AssertionError:
            got_ids = [g for g, _ in hits]
            want_ids = [g for g, _ in want]
            if sorted(got_ids) == sorted(want_ids):
                spread = max(abs(dict(hits).get(g, 0.0) - dict(want).get(g, 0.0))
                             for g in set(got_ids) | set(want_ids))
                if spread <= 1e-6:
                    tie_only += 1
                    continue
            if len(mismatches) < 5:
                mismatches.append(dict(cut=cut, phrases=list(p), op=o, got=got_ids, want=want_ids))
    return dict(query=quant_us(times), work=dict(work), filter_work=dict(filter_work),
                rank_checks=len(times), score_error=1.0 if mismatches else 0.0,
                tie_order_differences=tie_only, rank_mismatches=mismatches,
                samples=samples)


def query_of(t):
    return (t["eval_cut"], tuple(" ".join(ph) for ph in t["phrases"]), t["op"])


def run(a):
    global EXTENSION
    EXTENSION = a.extension.resolve()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        if a.corpus == "clark":
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
            wpath = HERE.parent / "round-180" / "manifest-ap-10009.json"
        frozen = json.loads(wpath.read_text())
        templates = frozen["templates"]
        digest = frozen["manifest"]["workload_sha256"]

        refs = {c: h.active_oracle(events, c) for c in cuts}
        expected = {}
        for t in templates:
            key = query_of(t)
            if key not in expected:
                expected[key] = h.native(refs[key[0]], key[1], key[2])
        for ref in refs.values():
            ref.close()

        # One archive: frequency index, then positions and pairs on top of it.
        path = folder / "combined.sqlite"
        db, _ = f.build(path, EXTENSION, events, "marginal", False)
        terms = cs.extract(db)            # positions must be read before the tape replaces docs_0
        tt.build_tape(db, path, events, "frequency")
        ids, _ = tt.vocabulary(db)
        db.commit()
        db.execute("VACUUM")
        base_bytes = path.stat().st_size

        tokdb = f.connect(":memory:", EXTENSION)
        _, endpoints = rj.build_pair_postings(db, tokdb, min_df=1)
        # Buy vocabulary, not individual posting lists: every pair whose two endpoints are
        # bought is stored, so a phrase nobody anticipated is still filterable.  The df/byte
        # rule buys expensive lists that reject almost nothing and is not used here.
        keep = rj.select_pairs_vocabulary(db, a.pairs_pct / 100.0 * base_bytes, endpoints, ids)
        db.execute("UPDATE pair_index_meta SET selective=1")
        db.execute("CREATE TABLE kept(pid INTEGER PRIMARY KEY)")
        db.executemany("INSERT INTO kept VALUES(?)", ((p,) for p in sorted(keep)))
        db.execute("DELETE FROM pair_postings WHERE pid NOT IN (SELECT pid FROM kept)")
        db.execute("DROP TABLE kept")
        chosen, spent = cs.greedy(cs.score_terms(terms, ids, "df", {}),
                                  a.positions_pct / 100.0 * base_bytes)
        db.execute("CREATE TABLE term_blocks(tid INTEGER PRIMARY KEY,n_postings INTEGER NOT NULL,"
                   "nblocks INTEGER NOT NULL,dir BLOB NOT NULL,body BLOB NOT NULL)")
        by_tid = {ids[t]: (s, e) for t, (s, e) in terms.items()}
        for tid in chosen:
            stats, enc = by_tid[tid]
            db.execute("INSERT INTO term_blocks VALUES(?,?,?,?,?)",
                       (tid, stats["df"], enc["blocks"], enc["dir"], enc["body"]))
        db.commit()
        db.execute("VACUUM")
        tokdb.close()
        archive_bytes = path.stat().st_size
        mean_frame = sum(len(raw) for _, _, raw in events) / len(events)

        index = BlockIndex(db, ids, True)
        filters = rj.Filters(db)
        model = CostModel(db, index, filters, mean_frame)

        proto = wl.protocols(templates, cuts)
        # A keeps all three splits because calibration needs the training split.  B reports
        # its held-out slice only, and C reports the temporal evaluation slice; the
        # selection slice of C is not re-measured because it is the same queries at an
        # earlier cutoff and would double the run time for no additional evidence.
        splits = {
            "A": {k: [query_of(t) for t in v] for k, v in proto["A"].items()},
            "B": dict(heldout=[query_of(t) for t in proto["B"]["heldout"]]),
            "C": dict(evaluation=[query_of(t) for t in proto["C"]["evaluation"]["templates"]]),
        }
        strategies = ("source", "positions", "pairs_source", "pairs_positions", "planner")
        rates = None
        if not a.only or "planner" in a.only:
            # Calibration: training split only, never the validation or held-out queries.
            train = [query_of(t) for t in proto["A"]["train"]]
            base_rates = {}
            rows = []
            for mode in ("source", "positions", "pairs_source"):
                got = measure(db, list(train), expected, index, filters, None, mode)
                base_rates[mode] = got
                rows.extend(got["samples"])
            # Least squares over per-query timings and counters, training split only:
            #   micros ~= source_reads * source_us + blocks * block_us + pair_bytes * pair_byte_us
            import numpy as np
            X = np.array([[r[1], r[2], r[3]] for r in rows], dtype=float)
            y = np.array([r[0] for r in rows], dtype=float)
            coef, *_ = np.linalg.lstsq(X, y, rcond=None)
            rates = dict(source_us=float(max(0.0, coef[0])),
                         block_us=float(max(0.0, coef[1])),
                         pair_byte_us=float(max(0.0, coef[2])),
                         calibration_train_queries=len(train),
                         calibration_samples=len(rows),
                         calibration={m: dict(median=v["query"]["median_us"],
                                              p95=v["query"]["p95_us"],
                                              work=v["work"]) for m, v in base_rates.items()})
            model.rates = rates
            print("RATES_JSON=" + json.dumps({k: v for k, v in rates.items()
                                              if k != "calibration"}), flush=True)
        out = {}
        for name in strategies:
            if a.only and name not in a.only:
                continue
            arms = {}
            for pname, parts in splits.items():
                arms[pname] = {}
                for split, queries in parts.items():
                    order = list(queries)
                    random.Random(182).shuffle(order)
                    arms[pname][split] = measure(db, order, expected, index, filters, model, name)
                    q = arms[pname][split]["query"]
                    print("ARM_JSON=" + json.dumps(dict(
                        name=name, protocol=pname, split=split, median=q["median_us"],
                        p95=q["p95_us"], p99=q["p99_us"], max=q["max_us"],
                        src=arms[pname][split]["work"].get("source_reads"),
                        err=arms[pname][split]["score_error"],
                        modes={k: v for k, v in arms[pname][split]["work"].items()
                               if k.startswith("mode_")}), default=str), flush=True)
            out[name] = dict(strategy=name, protocols=arms)
        db.close()
        result = dict(round=182, corpus=a.corpus, revisions=len(events),
                      manifest_sha256=manifest, workload_sha256=digest,
                      base_archive_bytes=base_bytes, archive_bytes=archive_bytes,
                      archive_overhead_fraction=archive_bytes / base_bytes,
                      pairs_pct=a.pairs_pct, positions_pct=a.positions_pct,
                      selected_terms=len(chosen), selected_pairs=len(keep),
                      mean_frame_bytes=mean_frame, rates=rates, arms=out,
                      limitations=[
                          "logical activation of stored bytes; no physical page I/O, no cold cache",
                          "the planner optimises estimated activated bytes, not measured latency",
                          "pair and position budgets are percentages of the frequency archive; "
                          "the measured combined archive is reported alongside",
                          "every ranking is compared with the native FTS5 oracle"])
        for name, blob in list(out.items()):
            for pname, parts in blob["protocols"].items():
                for split, cell in parts.items():
                    cell.pop("samples", None)
        if a.out.exists():
            old = json.loads(a.out.read_text())
            if old.get("manifest_sha256") == manifest and old.get("workload_sha256") == digest:
                old["arms"].update(result["arms"])
                result = old
        a.out.write_text(json.dumps(result, indent=2, default=str) + "\n")
        print("RESULT_JSON=" + json.dumps(dict(round=182, corpus=a.corpus, arms=len(out),
                                              archive=archive_bytes, base=base_bytes)))


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