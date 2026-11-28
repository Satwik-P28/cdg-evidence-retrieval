"""R183: phrase-level joint selection of positional materialisation.

R174 scored each term independently: a term earned a share of every candidate
opportunity it appeared in, and the optimiser bought the best value-per-byte ratios.  That
model cannot see interaction.  A phrase with three tokens is only answerable from
positions when *two* of its offsets are covered, so buying the single highest-value term of
each phrase can produce a set that covers many phrases once and none of them twice -- and
the positions then reject nothing.

This round replaces the additive model with a coverage objective over phrases:

    value(S) = sum of w(p) over training phrases p whose covered-token count is >= 2

where w(p) is the estimated source bytes that answering p would otherwise activate.  A
phrase contributes nothing until its second token is in S, so every term is valued by what
it *completes*, not by what it participates in.

Implemented selectors:

``joint_coverage``      greedy on the coverage objective (marginal completions per byte)
``pairwise``            greedy over whole phrase bundles, best bundle first
``local_swap``          joint_coverage followed by bounded multi-term swaps
``additive``            R174's per-term share model, the thing being replaced
``independent_df``      document frequency per byte, no workload at all (the control)

No submodularity is claimed.  Instead the exact optimum is enumerated over the top twelve
candidate terms and the greedy gap is reported as a measured number, so a reader can see
how much the greedy rule gives away rather than being told it is near-optimal.

Every budget is reported both as the estimated payload budget and as the measured physical
archive growth, and every archive is verified against the native FTS5 oracle.
"""
import argparse
import collections
import itertools
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
for _p in ("round-182", "round-181", "round-180", "round-174", "round-173", "round-158",
           "round-157", "round-165", "round-152", "round-141", "round-138", "round-136",
           "round-120"):
    sys.path.insert(0, str(HERE.parent / _p))

import forward_index as f  # noqa: E402
import token_tape as tt  # noqa: E402
from forward_index import h, tokens  # noqa: E402
from blocked_positions import BlockIndex, quant_us  # noqa: E402
import cost_selection as cs  # noqa: E402
import workload as wl  # noqa: E402
import planner as pl  # noqa: E402
import rejection as rj  # noqa: E402

EXTENSION = None
BUDGETS = (1, 2, 5, 10, 20)


def phrase_requirements(train, ids):
    """For each training phrase, the tids it needs and the value it is worth."""
    reqs = []
    for t in train:
        phrase = t["phrases"][0]
        tids = []
        for word in phrase:
            tid = ids.get(word.encode("utf-8"))
            if tid is None:
                tids = []
                break
            tids.append(tid)
        tids = list(dict.fromkeys(tids))
        if len(tids) < 2:
            continue
        reqs.append(dict(tids=tids, weight=max(1.0, t.get("est_cost_bytes") or 1.0),
                         phrase=phrase))
    return reqs


def coverage_objective(selected, reqs):
    return sum(r["weight"] for r in reqs if len(set(r["tids"]) & selected) >= 2)


def joint_coverage(costs, reqs, budget, max_steps=20000):
    """Greedy on completions per byte, with incremental marginal gains.

    ``gain[t]`` is the weight of phrases that a single additional token ``t`` would
    complete (exactly one of their tokens already selected).  It is maintained on every
    selection instead of being recomputed, so a step costs the incidences of the chosen
    token rather than a sweep over the vocabulary.
    """
    incid = collections.defaultdict(list)
    for i, r in enumerate(reqs):
        for tid in r["tids"]:
            incid[tid].append(i)
    counts = [0] * len(reqs)
    gain = collections.defaultdict(float)
    selected = set()
    spent = 0.0
    for _ in range(max_steps):
        best = None
        for tid, cost in costs.items():
            if tid in selected or spent + cost > budget:
                continue
            g = gain.get(tid, 0.0)
            if g <= 0:
                continue
            ratio = g / max(1.0, cost)
            if best is None or ratio > best[0]:
                best = (ratio, tid, cost)
        if best is None:
            # Every first token of a phrase completes nothing, so the marginal gain of the
            # first selection is zero for every term.  Seed instead with the term that can
            # participate in the most incomplete phrases per byte, which is what creates the
            # second-token completions the objective rewards.
            seed = None
            for tid, cost in costs.items():
                if tid in selected or spent + cost > budget:
                    continue
                potential = sum(1 for i in incid[tid] if counts[i] == 0)
                if potential <= 0:
                    continue
                ratio = potential / max(1.0, cost)
                if seed is None or ratio > seed[0]:
                    seed = (ratio, tid, cost)
            if seed is None:
                break
            best = seed
        _, tid, cost = best
        selected.add(tid)
        spent += cost
        for i in incid[tid]:
            before = counts[i]
            counts[i] = before + 1
            if before == 0:
                # One more token anywhere in this phrase would complete it.
                for other in reqs[i]["tids"]:
                    if other != tid:
                        gain[other] += reqs[i]["weight"]
            elif before == 1:
                # It has just been completed; no token can gain from it again.
                for other in reqs[i]["tids"]:
                    if other != tid:
                        gain[other] -= reqs[i]["weight"]
    return selected, spent


def pairwise_bundles(costs, reqs, budget):
    """Greedy over whole phrase bundles: complete a phrase before starting another."""
    remaining = list(range(len(reqs)))
    selected = set()
    spent = 0.0
    while True:
        best = None
        for idx in remaining:
            need = [t for t in reqs[idx]["tids"] if t not in selected]
            cost = sum(costs.get(t, 0.0) for t in need)
            if spent + cost > budget:
                continue
            ratio = reqs[idx]["weight"] / max(1.0, cost)
            if best is None or ratio > best[0]:
                best = (ratio, idx, need, cost)
        if best is None:
            break
        _, idx, need, cost = best
        selected.update(need)
        spent += cost
        remaining.remove(idx)
    return selected, spent


def local_swap(costs, reqs, budget, seed, rounds=4):
    """Bounded multi-term swaps: drop the weakest chosen terms, retry alternatives."""
    selected = set(seed)
    spent = sum(costs.get(t, 0.0) for t in selected)
    best_value = coverage_objective(selected, reqs)
    for _ in range(rounds):
        improved = False
        weakest = sorted(selected, key=lambda t: costs.get(t, 0.0))[:3]
        for drop in weakest:
            freed = spent - costs.get(drop, 0.0)
            cand = set(selected) - {drop}
            trial, trial_spent = joint_coverage(
                {t: c for t, c in costs.items() if t not in cand}, reqs, freed, max_steps=60)
            merged = cand | trial
            value = coverage_objective(merged, reqs)
            total = sum(costs.get(t, 0.0) for t in merged)
            if value > best_value and total <= budget:
                selected, spent, best_value = merged, total, value
                improved = True
                break
        if not improved:
            break
    return selected, spent


def additive(costs, reqs, budget):
    """R174's model: each term gets an equal share of every phrase it appears in."""
    value = collections.Counter()
    for r in reqs:
        share = r["weight"] / max(1, len(r["tids"]))
        for tid in r["tids"]:
            value[tid] += share
    ranked = sorted(costs, key=lambda t: (-(value[t] / max(1.0, costs[t])), t))
    selected = set()
    spent = 0.0
    for tid in ranked:
        if spent + costs[tid] > budget:
            continue
        selected.add(tid)
        spent += costs[tid]
    return selected, spent


def independent_df(costs, reqs, budget, ids, token_df):
    rated = []
    for tid, cost in costs.items():
        df = token_df.get(tid, 0)
        if not df:
            continue
        rated.append((df / max(1.0, cost), tid, cost))
    rated.sort(key=lambda r: (-r[0], r[1]))
    selected = set()
    spent = 0.0
    for _, tid, cost in rated:
        if spent + cost > budget:
            continue
        selected.add(tid)
        spent += cost
    return selected, spent


def exact_gap(costs, reqs, budget, top=12):
    """Exact optimum over the top candidate terms, versus greedy on the same subset.

    Reported as a measured ratio so no approximation guarantee has to be asserted.
    """
    incid = collections.defaultdict(float)
    for r in reqs:
        for tid in r["tids"]:
            incid[tid] += r["weight"]
    cand = sorted(costs, key=lambda t: (-incid.get(t, 0.0), t))[:top]
    subsets = []
    for k in range(len(cand) + 1):
        for combo in itertools.combinations(cand, k):
            cost = sum(costs[t] for t in combo)
            if cost > budget:
                continue
            subsets.append((coverage_objective(set(combo), reqs), combo, cost))
    if not subsets:
        return None
    best = max(subsets, key=lambda s: s[0])
    restricted = {t: costs[t] for t in cand}
    greedy_set, greedy_spent = joint_coverage(restricted, reqs, budget)
    greedy_value = coverage_objective(greedy_set, reqs)
    return dict(candidates=len(cand), subsets=len(subsets),
                exact_value=best[0], exact_cost=best[2],
                greedy_value=greedy_value, greedy_cost=greedy_spent,
                ratio=greedy_value / best[0] if best[0] else None)


def evaluate(db, queries, expected, index, strategy="positions"):
    return pl.measure(db, queries, expected, index, rj.Filters(db), None, strategy)


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
            key = pl.query_of(t)
            if key not in expected:
                expected[key] = h.native(refs[key[0]], key[1], key[2])
        for ref in refs.values():
            ref.close()

        base = folder / "base.sqlite"
        db, _ = f.build(base, EXTENSION, events, "marginal", False)
        terms = cs.extract(db)
        tt.build_tape(db, base, events, "frequency")
        ids, _ = tt.vocabulary(db)
        db.commit()
        db.execute("VACUUM")
        base_bytes = base.stat().st_size
        base_db = f.connect(base, EXTENSION)
        token_df = dict(base_db.execute("SELECT tid,n FROM token_postings"))
        base_db.close()

        proto = wl.protocols(templates, cuts)
        train = proto["A"]["train"]
        reqs = phrase_requirements(train, ids)
        costs = {ids[t]: float(s["posbytes"]) for t, (s, e) in terms.items() if t in ids}

        gaps = {pct: exact_gap(costs, reqs, pct / 100.0 * base_bytes) for pct in a.budgets}
        out = {}
        for pct in a.budgets:
            budget = pct / 100.0 * base_bytes
            selections = {
                "joint_coverage": joint_coverage(costs, reqs, budget),
                "pairwise": pairwise_bundles(costs, reqs, budget),
                "additive": additive(costs, reqs, budget),
                "independent_df": independent_df(costs, reqs, budget, ids, token_df),
            }
            seed, seed_spent = selections["joint_coverage"]
            selections["local_swap"] = local_swap(costs, reqs, budget, seed)
            for name, (chosen, spent) in selections.items():
                path = folder / ("arm-%s-%d.sqlite" % (name, pct))
                shutil.copyfile(base, path)
                dbx = f.connect(path, EXTENSION)
                dbx.execute("CREATE TABLE term_blocks(tid INTEGER PRIMARY KEY,n_postings INTEGER NOT NULL,"
                            "nblocks INTEGER NOT NULL,dir BLOB NOT NULL,body BLOB NOT NULL)")
                by_tid = {ids[t]: (s, e) for t, (s, e) in terms.items()}
                for tid in chosen:
                    stats, enc = by_tid[tid]
                    dbx.execute("INSERT INTO term_blocks VALUES(?,?,?,?,?)",
                                (tid, stats["df"], enc["blocks"], enc["dir"], enc["body"]))
                dbx.commit()
                dbx.execute("VACUUM")
                archive_bytes = path.stat().st_size
                index = BlockIndex(dbx, ids, True)
                arms = {}
                for split in ("heldout", "validation"):
                    queries = [pl.query_of(t) for t in proto["A"][split]]
                    arms["A_" + split] = evaluate(dbx, queries, expected, index)
                arms["B_heldout"] = evaluate(dbx, [pl.query_of(t) for t in proto["B"]["heldout"]],
                                             expected, index)
                dbx.close()
                path.unlink()
                out["%s-%d%%" % (name, pct)] = dict(
                    selector=name, budget_pct=pct, selected_terms=len(chosen),
                    selection_bytes=spent, archive_bytes=archive_bytes,
                    measured_increment_bytes=archive_bytes - base_bytes,
                    measured_fraction=archive_bytes / base_bytes,
                    splits=arms,
                    coverage_value=coverage_objective(chosen, reqs))
                q = arms["A_heldout"]["query"]
                print("ARM_JSON=" + json.dumps(dict(
                    name=name, pct=pct, terms=len(chosen),
                    inc=archive_bytes - base_bytes, p95=q["p95_us"], p99=q["p99_us"],
                    max=q["max_us"], src=arms["A_heldout"]["work"].get("source_reads"),
                    err=arms["A_heldout"]["score_error"])), flush=True)
        result = dict(round=183, corpus=a.corpus, revisions=len(events),
                      manifest_sha256=manifest, workload_sha256=digest,
                      base_archive_bytes=base_bytes, budgets=list(a.budgets),
                      train_phrases=len(reqs), exact_gap=gaps, arms=out,
                      limitations=[
                          "coverage objective uses training-split phrases only; held-out data "
                          "never selects or tunes a budget",
                          "no submodularity is claimed; the greedy gap is measured over the top "
                          "twelve terms, which is a lower bound on the true gap",
                          "weights are estimated source bytes, not measured per-query savings",
                          "logical activation; no physical page I/O and no cold cache"])
        a.out.write_text(json.dumps(result, indent=2, default=str) + "\n")
        print("RESULT_JSON=" + json.dumps(dict(round=183, corpus=a.corpus, arms=len(out),
                                              gaps={str(k): v["ratio"] if v else None
                                                    for k, v in gaps.items()})))


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--corpus", choices=("ap", "clark"), required=True)
    p.add_argument("--target", type=int, default=10000)
    p.add_argument("--extension", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--budgets", default="1,2,5,10,20")
    return p.parse_args()


if __name__ == "__main__":
    a = parse_args()
    a.budgets = [int(x) for x in a.budgets.split(",") if x]
    run(a)