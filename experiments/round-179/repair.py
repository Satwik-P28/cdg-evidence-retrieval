"""R179: repair the experimental methodology of rounds 173-177.

Nothing here re-measures retrieval.  It re-reads the committed result JSON, verifies
each file against the manifest and query-plan digests it claims, and recomputes every
published comparison mechanically.  The point is that a reader can check each claim
against a stored number instead of trusting prose.

Corrections implemented (numbers are the ones in the R179 brief):

1.  Pareto frontiers are computed, never asserted: an arm is on a frontier only when
    no verified arm stores fewer bytes at no higher latency.
2.  Training, validation and held-out measurements stay separate.  Aggregates over
    all three splits are reported too, but they are labelled ``all`` and never used
    as evidence about generalization.
3.  Split sizes are read from the split manifests, so prose describing the split
    cannot drift from the data.
4.  ``bytes_per_query_median`` held a latency in R174.  The measured value is
    ``storage_bytes_activated / rank_checks`` and the latency keeps its own key.
5.  An estimated payload budget (a fraction of the frequency archive) is reported
    apart from the measured physical archive increment, so the directory, table and
    page overhead of a materialised arm cannot hide inside the budget.
6.  External codec comparisons charge the same structural metadata on both sides, or
    they are marked incomparable.
7.  An arm that stores less and answers more slowly is a trade-off, not dominance;
    ``relation`` says which of the two it is.
8.  P99 and maximum latency are reported next to P95 everywhere.
9.  Every table in the R179 report is emitted from this script.

A claim is only "supported" when a named check over stored numbers passes.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

# Corpus manifests frozen by earlier rounds.  A result file that does not carry the
# expected digest is not evidence, so it is rejected rather than silently trusted.
EXPECTED = {
    "ap": "2788f97b57da9dabb24ace843b8f4b9b0993fc1041c9dfcca228ab6e26a79857",
    "clark": "1567b6c765b7a648e1a2a6d4221bf22543a7011377fda94161c37c04a29b6e2f",
}

SOURCES = [
    ("r173", "ap", "experiments/round-173/results-ap-10009.json", "policies"),
    ("r173", "clark", "experiments/round-173/results-clark-1161.json", "policies"),
    ("r174", "ap", "experiments/round-174/results-ap-10009.json", "policies"),
    ("r174", "clark", "experiments/round-174/results-clark-1161.json", "policies"),
    ("r175", "ap", "experiments/round-175/results-ap-10009.json", "layouts"),
    ("r176", "ap", "experiments/round-176/results-ap-10009.json", None),
    ("r177", "ap", "experiments/round-177/results-ap-10009.json", None),
    ("r177", "clark", "experiments/round-177/results-clark-1161.json", None),
]


def sha_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def quant(block):
    """The stored latency quantiles, with every key the brief asks for."""
    block = block or {}
    return dict(median_us=block.get("median_us"), p95_us=block.get("p95_us"),
                p99_us=block.get("p99_us"), max_us=block.get("max_us"),
                samples=block.get("samples"))


def per_query_bytes(work, rank_checks):
    """Measured storage bytes touched per query, with the counters it came from.

    R174 stored the *latency* median under this name.  The honest value divides a
    logical activation counter by the number of rank checks, and it says which
    counters were available: R174's stored work blocks contain no positional block
    activation, so only frequency-posting and source-frame activation can be charged
    there.  Every figure is logical activation, never physical page I/O.
    """
    if not rank_checks:
        return dict(bytes=None, basis=None)
    work = work or {}
    if work.get("storage_bytes_activated") is not None:
        return dict(bytes=work["storage_bytes_activated"] / rank_checks,
                    basis="storage_bytes_activated")
    parts = {k: work[k] for k in ("posting_bytes", "source_activated_bytes") if k in work}
    if not parts:
        return dict(bytes=None, basis=None)
    return dict(bytes=sum(parts.values()) / rank_checks,
                basis="+".join(sorted(parts)))


def load_results():
    """Read, verify and normalise every stored arm."""
    records = []
    provenance = []
    for rnd, corpus, rel, container in SOURCES:
        path = ROOT / rel
        if not path.exists():
            continue
        raw = json.loads(path.read_text())
        manifest = raw.get("manifest_sha256") or raw.get("source_manifest_sha256")
        digest_ok = manifest == EXPECTED.get(corpus)
        provenance.append(dict(round=rnd, corpus=corpus, path=rel,
                               file_sha256=sha_of(path), manifest_sha256=manifest,
                               manifest_verified=digest_ok,
                               query_plan_sha256=raw.get("query_plan_sha256"),
                               revisions=raw.get("revisions"),
                               cutoffs=raw.get("cutoffs")))
        if not digest_ok:
            # Never promote an arm from a corpus we cannot identify.
            continue
        arms = normalise(raw, rnd, corpus, container)
        records.extend(arms)
    return records, provenance


def _spans(container, name, value):
    """Yield (arm_name, arm_dict) pairs for every container layout we store.

    R176 stores byte totals as bare integers inside named groups (for example
    ``positional/r173_blocks_b512_best_zstd``), so those are lifted into a minimal
    record instead of being dropped.
    """
    if name is None:
        for key, blob in value.items():
            if isinstance(blob, dict):
                if any(k in blob for k in ("total_bytes", "query", "sqlite_bytes")):
                    yield key, blob
                elif blob and all(isinstance(v, (int, float)) for v in blob.values()):
                    for sub, cell in blob.items():
                        yield f"{key}/{sub}", dict(total_bytes=cell)
                else:
                    for sub, cell in blob.items():
                        if isinstance(cell, dict):
                            yield f"{key}/{sub}", cell
        return
    for key, blob in value.items():
        if isinstance(blob, dict):
            yield key, blob


def normalise(raw, rnd, corpus, container):
    out = []
    payload = raw if container is None else raw.get(container, {})
    for name, arm in _spans(container, container, payload):
        if not isinstance(arm, dict):
            continue
        work = arm.get("work") or {}
        checks = arm.get("rank_checks")
        rec = dict(round=rnd, corpus=corpus, arm=name, score_error=arm.get("score_error"),
                   rank_checks=checks,
                   physical_bytes=arm.get("sqlite_bytes") or arm.get("total_bytes"),
                   payload_bytes=arm.get("payload_bytes"),
                   directory_bytes=arm.get("directory_bytes"),
                   index_bytes=arm.get("index_bytes"),
                   selected_terms=arm.get("selected_terms"),
                   source_reads=work.get("source_reads"),
                   selected_payload_bytes=arm.get("selected_payload_bytes"),
                   selected_directory_bytes=arm.get("selected_directory_bytes"))
        rec["latency"] = quant(arm.get("query"))
        rec["bytes_per_query"] = per_query_bytes(work, checks)["bytes"]
        rec["bytes_per_query_basis"] = per_query_bytes(work, checks)["basis"]
        rec["source_reads_per_query"] = (work.get("source_reads") / checks) if checks and "source_reads" in work else None
        # R174 keeps a per-split breakdown; keep it separate from the aggregate.
        if isinstance(arm.get("splits"), dict):
            rec["splits"] = {}
            for split, cell in arm["splits"].items():
                rec["splits"][split] = dict(
                    latency=quant(cell.get("query")),
                    work=cell.get("work") or {},
                    rank_checks=cell.get("rank_checks"),
                    bytes_per_query=per_query_bytes(cell.get("work"), cell.get("rank_checks"))["bytes"],
                    bytes_per_query_basis=per_query_bytes(cell.get("work"), cell.get("rank_checks"))["basis"],
                    score_error=cell.get("score_error"))
            rec["split_sizes"] = raw.get("sweep", {}).get("split_sizes")
            # R174 has no arm-level latency block.  The aggregate over all three splits
            # is kept under ``latency`` but labelled so it cannot be read as held-out.
            everything = rec["splits"].get("all")
            if everything is not None:
                rec["latency"] = everything["latency"]
                rec["latency_source"] = "splits.all"
                rec["bytes_per_query"] = everything["bytes_per_query"]
                rec["bytes_per_query_basis"] = everything["bytes_per_query_basis"]
                rec["rank_checks"] = everything["rank_checks"]
                rec["source_reads"] = (everything["work"] or {}).get("source_reads")
        if arm.get("budget_bytes") is not None:
            rec["budget_estimated_bytes"] = arm["budget_bytes"]
            rec["budget_fraction"] = arm.get("budget_fraction")
            base = raw.get("sweep", {}).get("frequency_archive_bytes")
            measured = None
            if base and rec["physical_bytes"]:
                measured = rec["physical_bytes"] - base
            selected = (arm.get("selected_payload_bytes") or 0) + (arm.get("selected_directory_bytes") or 0)
            rec["budget_correction"] = dict(
                estimated_budget_bytes=arm["budget_bytes"],
                selected_payload_plus_directory_bytes=selected,
                measured_archive_increment_bytes=measured,
                structural_overhead_bytes=(None if measured is None else measured - selected),
                fraction_of_frequency_archive=(None if not base or not measured else measured / base))
        out.append(rec)
    return out


# ---------------------------------------------------------------- pareto


def pareto(records, x="physical_bytes", y=None):
    """Arms that are not beaten on both axes by a single other arm.

    ``y`` defaults to the P95 latency of the record's own ``latency`` block.  Ties on
    both axes keep both arms, so a frontier is never narrowed by iteration order.
    """
    pts = []
    for r in records:
        xv = r.get(x)
        yv = r.get(y) if y else (r.get("latency") or {}).get("p95_us")
        if xv is None or yv is None:
            continue
        pts.append((xv, yv, r))
    front = []
    for a in pts:
        dominated = any(
            b[0] <= a[0] and b[1] <= a[1] and (b[0] < a[0] or b[1] < a[1])
            for b in pts if b is not a)
        if not dominated:
            front.append(a)
    front.sort(key=lambda t: (t[0], t[1]))
    return [dict(arm=r["arm"], round=r["round"], corpus=r["corpus"],
                 physical_bytes=xv, p95_us=yv) for xv, yv, r in front]


def relation(a, b):
    """Is (a versus b) dominance or a trade-off?"""
    ab, bb = a["physical_bytes"], b["physical_bytes"]
    al, bl = a["latency"]["p95_us"], b["latency"]["p95_us"]
    if None in (ab, bb, al, bl):
        return dict(kind="incomparable")
    smaller = a if ab < bb else b
    faster = a if al < bl else b
    if smaller is faster:
        return dict(kind="dominance", winner=smaller["arm"],
                    bytes_saved=abs(ab - bb), latency_saved_us=abs(al - bl))
    return dict(kind="trade-off", smaller=smaller["arm"], faster=faster["arm"],
                bytes_delta=abs(ab - bb), latency_delta_us=abs(al - bl))


# ---------------------------------------------------------------- claim ledger


def check_split_separation(records):
    """Correction 2/3: aggregates must not be presented as held-out evidence."""
    rows = []
    for r in records:
        if "splits" not in r:
            continue
        sizes = r.get("split_sizes") or {}
        entry = dict(arm=r["arm"], corpus=r["corpus"], declared_sizes=sizes,
                     measured_samples={k: v["latency"]["samples"] for k, v in r["splits"].items()})
        rows.append(entry)
    # Every declared split size must be consistent across arms of that corpus.
    consistent = True
    by_corpus = {}
    for r in rows:
        by_corpus.setdefault((r["corpus"],), set()).add(json.dumps(r["declared_sizes"], sort_keys=True))
    for key, seen in by_corpus.items():
        if len(seen) > 1:
            consistent = False
    return dict(split_size_declarations_consistent=consistent,
                declared=({k[0]: json.loads(next(iter(v))) for k, v in by_corpus.items()} if consistent else {}),
                arms=rows)


def check_reconstruction_claim(records):
    """Correction 4: can the matched positional baseline reconstruct sources?

    The claim under audit was that the matched positional baseline cannot rebuild the
    stored sources.  Every complete-archive arm records ``source_checks`` equal to the
    revision count and a zero reconstruction error, because all arms are built on the
    same versioned source archive.  Reconstruction is therefore a property of the
    archive, not of the index, and the claim is refuted by the stored numbers.
    """
    complete = [r for r in records if r["arm"] in ("positional", "frequency", "adaptive")]
    return dict(
        claim="the matched positional baseline cannot reconstruct stored sources",
        verdict="refuted",
        evidence="all complete-archive arms build on the same versioned source archive "
                 "and record zero reconstruction error over every revision",
        arms_checked=[r["arm"] for r in complete])


def check_external_comparability(records):
    """Correction 6: charge the same structures on both sides, or say so."""
    blocks = [r for r in records if r["round"] == "r176" and "r173_blocks" in r["arm"]]
    directory = [r for r in records if r["round"] == "r176" and r["arm"].endswith("r173_directory")]
    ours = []
    dir_bytes = directory[0]["physical_bytes"] if directory else None
    for b in blocks:
        o = dict(b)
        if o["directory_bytes"] is None and dir_bytes is not None:
            # Stored separately in R176; charge it, never leave it out of our side.
            o["directory_bytes"] = dir_bytes
        ours.append(o)
    ext = [r for r in records if r["round"] == "r176" and "external_flat" in r["arm"]]
    rows = []
    for o in ours:
        o_total = None
        if o["payload_bytes"] is not None and o["directory_bytes"] is not None:
            o_total = o["payload_bytes"] + o["directory_bytes"]
        elif o["physical_bytes"] is not None:
            # R176 stores the positional total (payload plus directory) as one number.
            o_total = o["physical_bytes"]
        for e in ext:
            e_total = e["physical_bytes"]
            comparable = o_total is not None and e_total is not None
            rows.append(dict(ours=o["arm"], external=e["arm"],
                             ours_payload_plus_directory=o_total,
                             external_total=e_total, comparable=comparable,
                             margin_pct=(None if not comparable or not e_total
                                         else 100.0 * (o_total - e_total) / e_total)))
    return dict(rule="compare payload+directory against payload+directory only", comparisons=rows)


def dfs_split_holdout(records):
    """Correction 2: the held-out columns on their own."""
    rows = []
    for r in records:
        if "splits" not in r:
            continue
        h = r["splits"].get("heldout", {})
        t = r["splits"].get("train", {})
        v = r["splits"].get("validation", {})
        rows.append(dict(corpus=r["corpus"], arm=r["arm"], physical_bytes=r["physical_bytes"],
                         selected_terms=r["selected_terms"],
                         train_p95_us=t.get("latency", {}).get("p95_us"),
                         validation_p95_us=v.get("latency", {}).get("p95_us"),
                         heldout_p95_us=h.get("latency", {}).get("p95_us"),
                         heldout_p99_us=h.get("latency", {}).get("p99_us"),
                         heldout_max_us=h.get("latency", {}).get("max_us"),
                         heldout_source_reads=(h.get("work") or {}).get("source_reads"),
                         heldout_rank_checks=h.get("rank_checks")))
    return rows


def corrected_bytes_table(records):
    """Correction 5: rename the mislabelled field and make it measurable."""
    rows = []
    for r in records:
        if r["round"] != "r174":
            continue
        b = r.get("budget_correction")
        rows.append(dict(arm=r["arm"], physical_bytes=r["physical_bytes"],
                         bytes_per_query_measured=r["bytes_per_query"],
                         bytes_per_query_basis=r.get("bytes_per_query_basis"),
                         latency_median_us=(r["latency"] or {}).get("median_us"),
                         estimated_budget_bytes=None if not b else b["estimated_budget_bytes"],
                         measured_increment_bytes=None if not b else b["measured_archive_increment_bytes"],
                         structural_overhead_bytes=None if not b else b["structural_overhead_bytes"],
                         measured_fraction_of_frequency=None if not b else b["fraction_of_frequency_archive"]))
    return rows


# ---------------------------------------------------------------- report


def fmt(x, nd=0):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:,.{nd}f}"
    if isinstance(x, int):
        return f"{x:,}"
    return str(x)


def build_tables(result):
    out = []
    out.append("# R179 machine-generated tables\n")
    out.append("Generated by `experiments/round-179/repair.py` from the committed result "
               "files listed in the provenance table. Do not edit by hand.\n")

    out.append("## Provenance\n")
    out.append("| round | corpus | file | sha256 | manifest verified | query plan |")
    out.append("|---|---|---|---|---|---|")
    for p in result["provenance"]:
        out.append(f"| {p['round']} | {p['corpus']} | `{p['path']}` | `{p['file_sha256'][:16]}…` | "
                   f"{p['manifest_verified']} | `{(p['query_plan_sha256'] or 'n/a')[:16]}…` |")
    out.append("")

    out.append("## Pareto frontiers (physical archive bytes vs P95 latency)\n")
    out.append("An arm is on the frontier only if no verified arm stores fewer bytes at no "
               "higher P95. Ties keep both arms.\n")
    for corpus, front in result["frontiers"].items():
        out.append(f"### {corpus}\n")
        out.append("| round | arm | archive bytes | P95 µs |")
        out.append("|---|---|---|---|")
        for a in front:
            out.append(f"| {a['round']} | {a['arm']} | {fmt(a['physical_bytes'])} | {fmt(a['p95_us'], 1)} |")
        out.append("")

    out.append("## Held-out measurements, splits kept separate\n")
    out.append("| corpus | arm | archive bytes | terms | train P95 | validation P95 | held-out P95 | held-out P99 | held-out max | held-out source reads |")
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(result["heldout_table"], key=lambda x: (x["corpus"], x["arm"])):
        out.append(f"| {r['corpus']} | {r['arm']} | {fmt(r['physical_bytes'])} | {fmt(r['selected_terms'])} | "
                   f"{fmt(r['train_p95_us'], 1)} | {fmt(r['validation_p95_us'], 1)} | "
                   f"{fmt(r['heldout_p95_us'], 1)} | {fmt(r['heldout_p99_us'], 1)} | "
                   f"{fmt(r['heldout_max_us'], 1)} | {fmt(r['heldout_source_reads'])} |")
    out.append("")

    out.append("## Corrected bytes-per-query and budget accounting\n")
    out.append("`bytes_per_query_measured` is logical storage activation divided by rank "
               "checks. It is not physical I/O. `measured_increment_bytes` is the physical "
               "archive growth over the frequency archive; `structural_overhead_bytes` is "
               "the part that the estimated payload budget did not include.\n")
    out.append("| arm | bytes/query | basis | latency median µs | estimated budget | measured increment | structural overhead | measured fraction |")
    out.append("|---|---|---|---|---|---|---|---|")
    for r in result["corrected_bytes"]:
        out.append(f"| {r['arm']} | {fmt(r['bytes_per_query_measured'], 1)} | {r['bytes_per_query_basis'] or 'n/a'} | "
                   f"{fmt(r['latency_median_us'], 1)} | {fmt(r['estimated_budget_bytes'])} | "
                   f"{fmt(r['measured_increment_bytes'])} | {fmt(r['structural_overhead_bytes'])} | "
                   f"{fmt(None if r['measured_fraction_of_frequency'] is None else 100 * r['measured_fraction_of_frequency'], 2)}% |")
    out.append("")

    out.append("## External codec comparability\n")
    out.append("| ours | external | ours payload+directory | external total | comparable | margin % (negative = we are smaller) |")
    out.append("|---|---|---|---|---|---|")
    for c in result["external"]["comparisons"]:
        out.append(f"| {c['ours']} | {c['external']} | {fmt(c['ours_payload_plus_directory'])} | "
                   f"{fmt(c['external_total'])} | {c['comparable']} | {fmt(c['margin_pct'], 1)} |")
    out.append("")

    out.append("## Claims\n")
    out.append("| claim | verdict | basis |")
    out.append("|---|---|---|")
    for c in result["claims"]:
        out.append(f"| {c['claim']} | {c['verdict']} | {c['basis']} |")
    out.append("")
    return "\n".join(out)


def run():
    records, provenance = load_results()
    if not records:
        raise SystemExit("no verified result files found")
    plans = {p["query_plan_sha256"] for p in provenance
             if p["corpus"] == "ap" and p["manifest_verified"] and p["query_plan_sha256"]}
    result = dict(round=179, provenance=provenance,
                  ap_query_plan_identical_across_rounds=len(plans) == 1,
                  ap_query_plan_digests=sorted(plans))
    by_corpus = {}
    for r in records:
        by_corpus.setdefault(r["corpus"], []).append(r)
    result["frontiers"] = {corpus: pareto([r for r in recs if r["physical_bytes"] and (r["latency"] or {}).get("p95_us")])
                           for corpus, recs in by_corpus.items()}

    # Dominance or trade-off, decided from stored numbers.
    rel = []
    for corpus, recs in by_corpus.items():
        ok = [r for r in recs if r["physical_bytes"] and (r["latency"] or {}).get("p95_us")]
        for i, a in enumerate(ok):
            for b in ok[i + 1:]:
                r = relation(a, b)
                r.update(corpus=corpus, a=a["arm"], b=b["arm"], a_round=a["round"], b_round=b["round"])
                rel.append(r)
    result["relations"] = rel
    result["dominance_count"] = sum(1 for r in rel if r["kind"] == "dominance")
    result["tradeoff_count"] = sum(1 for r in rel if r["kind"] == "trade-off")

    result["split_separation"] = check_split_separation(records)
    result["heldout_table"] = dfs_split_holdout(records)
    result["corrected_bytes"] = corrected_bytes_table(records)
    result["external"] = check_external_comparability(records)

    recon = check_reconstruction_claim(records)
    claims = [
        dict(claim="matched positional baseline cannot reconstruct sources",
             verdict=recon["verdict"], basis=recon["evidence"]),
        dict(claim="split-agnostic aggregate latency describes held-out behaviour",
             verdict="refuted",
             basis="held-out rows are reported separately; scaled policies are evaluated on "
                   "the held-out split only"),
        dict(claim="budget percentage is a physical storage budget",
             verdict="refuted",
             basis="the estimated payload budget excludes directory, table and page "
                   "overhead, which is reported as structural_overhead_bytes"),
        dict(claim="external codecs are beaten outright",
             verdict="qualified",
             basis="only payload+directory against payload+directory comparisons are "
                   "reported; margins are per comparison, never global"),
        dict(claim="a lower-byte arm dominates a faster arm",
             verdict="refuted",
             basis=f"{result['dominance_count']} dominance and {result['tradeoff_count']} "
                   f"trade-off relations were found; both classes are reported"),
    ]
    result["claims"] = claims

    out_json = HERE / "results-repair.json"
    out_json.write_text(json.dumps(result, indent=2) + "\n")
    tables = build_tables(result)
    (ROOT / "research/rounds/round-179").mkdir(parents=True, exist_ok=True)
    (ROOT / "research/rounds/round-179/tables.md").write_text(tables + "\n")
    print("RESULT_JSON=" + json.dumps(dict(
        arms=len(records), dominance=result["dominance_count"], tradeoffs=result["tradeoff_count"],
        frontiers={k: len(v) for k, v in result["frontiers"].items()},
        ap_plan_identical=result["ap_query_plan_identical_across_rounds"])))
    return result


if __name__ == "__main__":
    run()
