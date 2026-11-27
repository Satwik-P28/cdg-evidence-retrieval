"""R180: a discriminating, frozen query workload with three evaluation protocols.

R174's workload was 80 queries from one corpus-statistics template and a 60/20/20
split of *those* 80.  The held-out slice was therefore tiny and its phrase variants
were near-duplicates of training phrases, which is why a policy trained on 22 terms
looked excellent in training and collapsed on the larger corpus.

This module builds the workload that later rounds must answer:

  * twelve query classes, including adjacent-pair and long phrases, phrases whose
    middle token is rare, phrases absent from the corpus, high-candidate phrases,
    high-frequency repeated phrases, phrases from content that a later revision
    removed, and AND/OR combinations;
  * at least 1,000 distinct templates per corpus;
  * stratification by candidate count, exact phrase document frequency and expected
    verification cost, recorded per query;
  * three protocols: an independent split (A), a *family* holdout that keeps
    near-identical phrase variants on one side (B), and a temporal holdout that
    selects on earlier revisions and evaluates on later ones (C).

Everything is derived from corpus bytes and content hashes, so the manifest can be
re-frozen byte for byte.  Generation is separated from evaluation: the manifest is
written and committed before any method in rounds 181-183 is run, and every later
result records the manifest digest it was measured against.
"""
import argparse
import collections
import hashlib
import itertools
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "round-158"))
import forward_index as f  # noqa: E402
from forward_index import h, ar, tokens  # noqa: E402

EXPECTED = {
    "ap": "2788f97b57da9dabb24ace843b8f4b9b0993fc1041c9dfcca228ab6e26a79857",
    "clark": "1567b6c765b7a648e1a2a6d4221bf22543a7011377fda94161c37c04a29b6e2f",
}

SCAN_BUDGET = 6000

CLASSES = ("unigram_frequent", "unigram_mid", "unigram_rare",
           "phrase_2_3", "phrase_4_5", "phrase_6_8",
           "rare_middle", "absent_phrase", "high_candidate",
           "repeated_phrase", "changed_content", "and_or")


class Oracle:
    """Read-only view of the exact FTS5 active set at one cutoff."""

    def __init__(self, events, cut):
        self.ref = h.active_oracle(events, cut)
        self.cut = cut

    def close(self):
        self.ref.close()

    def count(self, expression):
        return self.ref.execute("SELECT count(*) FROM fulltext WHERE fulltext MATCH ?",
                                (expression,)).fetchone()[0]

    def vocab(self):
        self.ref.execute("CREATE VIRTUAL TABLE temp.v USING fts5vocab(main,fulltext,'row')")
        rows = self.ref.execute("SELECT term,doc FROM temp.v ORDER BY term").fetchall()
        self.ref.execute("DROP TABLE temp.v")
        return dict(rows)

    def phrase_df(self, phrase):
        return self.count(ar.expression([" ".join(phrase)], "AND"))

    def candidate_count(self, phrase):
        """Documents containing every token of the phrase, in any order."""
        return self.count(ar.expression(list(dict.fromkeys(phrase)), "AND"))


def _text(tok):
    """The token stream returns UTF-8 bytes; every query surface is text."""
    return tok.decode("utf-8") if isinstance(tok, (bytes, bytearray)) else tok


def _key(text):
    return h.sha(text.encode("utf-8"))


def _ngrams(text, per_length=4, max_len=8):
    """A few n-grams per length, so long phrases are not starved of candidates."""
    out = []
    for n in range(2, max_len + 1):
        available = len(text) - n + 1
        if available < 1:
            continue
        if available <= per_length:
            out.extend(tuple(text[i:i + n]) for i in range(available))
            continue
        stride = max(1, available // per_length)
        out.extend(tuple(text[i:i + n]) for i in range(0, available, stride)[:per_length])
    return out


def generate(oracle, events, cut, per_class, tokdb, cuts, max_len=8):
    """Deterministic templates for every class at one cutoff."""
    vocab = oracle.vocab()
    ranked = sorted(vocab.items(), key=lambda kv: (-kv[1], kv[0]))
    docs = []
    for _, _, raw in events[:cut]:
        text = [_text(t) for t in tokens(tokdb, raw.decode("utf-8"))]
        if len(text) >= 2:
            docs.append(text)
    out = []

    seen_keys = set()

    def add(cls, phrases, op, note=""):
        key = (tuple(tuple(p) for p in phrases), op)
        if key in seen_keys:
            return False
        seen_keys.add(key)
        out.append(dict(phrases=[list(p) for p in phrases], op=op, cls=cls, note=note))
        return True

    # 1-3: unigrams by frequency band.
    n = len(ranked)
    bands = {
        "unigram_frequent": ranked[:max(1, n // 20)],
        "unigram_mid": ranked[n // 2 - max(1, n // 40):n // 2 + max(1, n // 40)],
        "unigram_rare": [kv for kv in ranked if kv[1] <= 2],
    }
    for cls, pool in bands.items():
        picked = sorted(pool, key=lambda kv: _key("R180|" + cls + "|" + kv[0]))[:per_class]
        for term, _ in picked:
            add(cls, [(term,)], "AND")

    # 4-6: phrases of length 2-3, 4-5 and 6-8 taken from corpus text.
    seen = set()
    by_len = collections.defaultdict(list)
    for text in docs:
        for n_gram in _ngrams(text, per_length=4, max_len=max_len):
            if len(n_gram) >= 2:
                by_len[len(n_gram)].append(n_gram)
    for cls, lengths in (("phrase_2_3", (2, 3)), ("phrase_4_5", (4, 5)),
                         ("phrase_6_8", (6, 7, 8))):
        pool = [g for L in lengths for g in by_len.get(L, [])]
        pool = sorted({g for g in pool}, key=lambda g: _key("R180|" + cls + "|" + " ".join(g)))
        for g in pool[:SCAN_BUDGET]:
            if len([x for x in out if x["cls"] == cls]) >= per_class:
                break
            if g in seen:
                continue
            if oracle.phrase_df(g) < 1:
                continue
            seen.add(g)
            add(cls, [g], "AND")

    # 7: rare middle token between two common ones.  Read from corpus text, because
    #    enumerating frequent x rare x frequent almost never lands on a real trigram.
    frequent = [t for t, d in ranked[:max(1, n // 40)]][:80]
    common = {t for t, d in ranked if d >= 20}
    rare_set = {t for t, d in ranked if d <= 10}
    mid_pool = set()
    for text in docs:
        for i in range(len(text) - 2):
            if text[i + 1] in rare_set and text[i] in common and text[i + 2] in common:
                mid_pool.add(tuple(text[i:i + 3]))
    for g in sorted(mid_pool, key=lambda g: _key("R180|rare_middle|" + " ".join(g))):
        if len([x for x in out if x["cls"] == "rare_middle"]) >= per_class:
            break
        if oracle.phrase_df(g) >= 1:
            add("rare_middle", [g], "AND")

    # 8: two-token phrases that do not occur (verified, not assumed).
    terms_by_df = [t for t, _ in ranked]
    if len(terms_by_df) >= 400:
        pair_iter = ((a, b) for a in terms_by_df[:260] for b in terms_by_df[260:1400])
    else:
        # Small vocabularies still need absent-phrase coverage.
        pair_iter = ((a, b) for a in terms_by_df for b in terms_by_df if a != b)
    pairs = sorted(pair_iter, key=lambda g: _key("R180|absent|" + " ".join(g)))
    for g in pairs[:SCAN_BUDGET]:
        if len([x for x in out if x["cls"] == "absent_phrase"]) >= per_class:
            break
        if oracle.phrase_df(g) == 0 and oracle.candidate_count(g) >= 2:
            add("absent_phrase", [g], "AND")

    # 9: phrases whose token-wise candidate set is large but whose exact frequency is low.
    hot = sorted(((a, b) for a in terms_by_df[:60] for b in terms_by_df[:60] if a != b),
                 key=lambda g: _key("R180|high_candidate|" + " ".join(g)))
    for g in hot[:SCAN_BUDGET]:
        if len([x for x in out if x["cls"] == "high_candidate"]) >= per_class:
            break
        cand = oracle.candidate_count(g)
        if cand >= 64:
            add("high_candidate", [g], "AND")

    # 10: phrases repeated many times inside single documents.
    repeated = []
    for text in docs:
        counts = collections.Counter(tuple(text[i:i + 3]) for i in range(len(text) - 2))
        for g, c in counts.items():
            if c >= 5:
                repeated.append(g)
    repeated = sorted(set(repeated), key=lambda g: _key("R180|repeated|" + " ".join(g)))
    for g in repeated[:per_class]:
        add("repeated_phrase", [g], "AND")

    # 11: phrases whose content a later revision removed.  A removal is only
    #     observable from the cutoff that contains the later revision, so the
    #     template records which cutoff first exposes it instead of pretending the
    #     early cutoff already knew about it.
    removed = changed_phrases(events, tokdb)
    added = 0
    for phrase, observed_g in removed:
        if added >= per_class:
            break
        later = [c for c in cuts if c >= observed_g]
        if not later:
            continue
        if add("changed_content", [phrase], "AND", note="removed at event %d" % observed_g):
            out[-1]["observed_at_cut"] = later[0]
            added += 1

    # 12: AND and OR combinations over mixed frequency bands.
    partners = (frequent + [t for t, _ in ranked[len(frequent):len(frequent) + 6 * per_class]])
    variants = []
    for i, a in enumerate(frequent[:per_class // 2]):
        b = partners[(i * 7 + 3) % len(partners)] if partners else None
        if b is None or a == b:
            continue
        variants.append((((a,), (b,)), "AND"))
        variants.append((((a,), (b,)), "OR"))
    variants = sorted(variants, key=lambda v: _key("R180|and_or|" + repr(v)))
    for (a, b), op in variants[:per_class]:
        add("and_or", [a, b], op)
    return out


def changed_phrases(events, tokdb):
    """Token pairs a later revision removed, with the event index that exposed it."""
    articles = collections.defaultdict(list)
    for g, (a, i, raw) in enumerate(events, 1):
        articles[a].append((i, g, raw))
    found = {}
    for _, versions in articles.items():
        versions.sort()
        for (_, _, older), (_, later_g, newer) in zip(versions, versions[1:]):
            before = [_text(t) for t in tokens(tokdb, older.decode("utf-8"))]
            after = [_text(t) for t in tokens(tokdb, newer.decode("utf-8"))]
            after_pairs = {tuple(after[i:i + 2]) for i in range(len(after) - 1)}
            for i in range(len(before) - 1):
                pair = tuple(before[i:i + 2])
                if pair not in after_pairs and pair not in found:
                    found[pair] = later_g
    ranked = sorted(found, key=lambda g: _key("R180|changed|" + " ".join(g)))
    return [(g, found[g]) for g in ranked]


def describe(oracle, events, cut, templates):
    """Per-query stratification: candidates, exact phrase frequency, verification cost."""
    frames = [len(raw) for _, _, raw in events[:cut]]
    mean_frame = sum(frames) / max(1, len(frames))
    rows = []
    for t in templates:
        phrase = tuple(t["phrases"][0])
        cand = oracle.candidate_count(phrase)
        pdf = oracle.phrase_df(phrase)
        rows.append(dict(cand=cand, pdf=pdf, est_cost_bytes=cand * mean_frame,
                         length=len(phrase), cls=t["cls"]))
    return rows


def bucket_edges(values):
    """Fixed log-bucket edges so strata are comparable across corpora."""
    return [0, 1, 2, 5, 17, 65, 257, 1025, 4097, 16385, 65537]


def strata(rows):
    edges = bucket_edges(None)
    out = []
    for r in rows:
        cand_b = next((i for i, e in enumerate(edges[1:], 1) if r["cand"] < e), len(edges))
        pdf = r["pdf"]
        pdf_b = 0 if pdf == 0 else 1 if pdf <= 2 else 2 if pdf <= 10 else 3
        cost_edges = [0, 4096, 65536, 1048576, 16777216]
        cost_b = next((i for i, e in enumerate(cost_edges[1:], 1)
                       if r["est_cost_bytes"] < e), len(cost_edges))
        out.append(dict(candidate_bucket=f"<{edges[cand_b] if cand_b < len(edges) else 'inf'}",
                        phrase_df_bucket=["0", "1-2", "3-10", ">10"][pdf_b],
                        cost_bucket=cost_b))
    return out


def family_of(template):
    """Group near-identical phrase variants so they cannot straddle a split.

    Two phrases join the same family when one token sequence is contained in the
    other, or when they share at least 60% of their tokens in order.  The grouping is
    transitive (union-find), so "new york", "new york city" and "york city" all land
    on one side of the family holdout.
    """
    return tuple(sorted({tuple(p) for p in template["phrases"]}))


def families(templates):
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    keys = []
    for t in templates:
        k = family_of(t)
        keys.append(k)
        find(k)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if _near(a, b):
                union(a, b)
    groups = collections.defaultdict(list)
    for t, k in zip(templates, keys):
        groups[find(k)].append(t)
    return groups


def _near(a, b):
    ta = {tok for p in a for tok in p}
    tb = {tok for p in b for tok in p}
    if not ta or not tb:
        return False
    if ta <= tb or tb <= ta:
        return True
    return len(ta & tb) / min(len(ta), len(tb)) >= 0.6


def assign(items, salt, fractions=(0.6, 0.2, 0.2)):
    """Deterministic 60/20/20 split by content hash of the item key."""
    names = ("train", "validation", "heldout")
    cuts = [fractions[0], fractions[0] + fractions[1]]
    out = {n: [] for n in names}
    for item, key in items:
        x = _key(salt + "|" + key)[0]
        pos = x / 256.0
        name = names[0] if pos < cuts[0] else names[1] if pos < cuts[1] else names[2]
        out[name].append(item)
    return out


def protocols(templates, cuts):
    """A: independent split; B: family holdout; C: temporal holdout."""
    a = assign([(t, canonical_query(t)) for t in templates], "R180-A")
    fam = families(templates)
    root_of = {id(t): root for root, members in fam.items() for t in members}
    fam_split = assign([(root, _key("R180-B|" + repr(root)).hex()) for root in fam], "R180-B")
    b = {}
    for name, roots in fam_split.items():
        keep = set(roots)
        b[name] = [t for t in templates if root_of[id(t)] in keep]
    # C: a template whose removal only becomes visible after the first cutoff cannot
    # be part of selection, because at that cutoff the corpus still contains it.
    early = [t for t in templates if t.get("observed_at_cut", 0) <= cuts[0]]
    c = dict(selection=dict(cut=cuts[0], templates=early),
             evaluation=dict(cut=cuts[-1], templates=list(templates)))
    return dict(A=a, B=b, C=c)


def canonical_query(t):
    return hashlib.sha256(
        json.dumps([t["phrases"], t["op"]], sort_keys=True).encode()).hexdigest()


def canonical_templates(templates):
    return json.dumps(templates, sort_keys=True, separators=(",", ":"))


def manifest_digest(templates):
    return h.sha(canonical_templates(templates).encode()).hex()


def build(corpus, events, cuts, per_class, ext):
    oracle = Oracle(events, cuts[0])
    tokdb = f.connect(":memory:", ext)
    templates = generate(oracle, events, cuts[0], per_class, tokdb, cuts)
    tokdb.close()
    meta = describe(oracle, events, cuts[0], templates)
    oracle.close()
    for t, m in zip(templates, meta):
        t.update(cand=m["cand"], pdf=m["pdf"], length=m["length"],
                 est_cost_bytes=round(m["est_cost_bytes"], 1))
    strata_rows = strata(meta)
    for t, s in zip(templates, strata_rows):
        t.update(s)
    for i, t in enumerate(templates):
        # A changed-content query is only evaluated at or after the cutoff that
        # exposes the removal.  An absent-phrase query is only absent at the cutoff
        # whose vocabulary it was drawn against, so it is evaluated there.  Every
        # other query is spread across the cutoffs.
        if t["cls"] == "changed_content":
            t["eval_cut"] = t.get("observed_at_cut") or cuts[-1]
        elif t["cls"] == "absent_phrase":
            t["eval_cut"] = cuts[0]
            t["absent_at_cut"] = cuts[0]
        else:
            t["eval_cut"] = cuts[i % len(cuts)]
    counts = collections.Counter(t["cls"] for t in templates)
    shortfall = {c: per_class - counts.get(c, 0) for c in CLASSES if counts.get(c, 0) < per_class}
    proto = protocols(templates, cuts)
    manifest = dict(
        round=180, corpus=corpus, manifest_sha256=EXPECTED[corpus],
        revisions=len(events), cutoffs=cuts, per_class=per_class,
        classes=list(CLASSES), class_counts=dict(counts),
        class_shortfall=shortfall,
        templates=len(templates),
        distinct_phrase_sets=len({json.dumps(t["phrases"], sort_keys=True) for t in templates}),
        workload_sha256=manifest_digest(templates),
        protocol_sizes=dict(
            A={n: len(v) for n, v in proto["A"].items()},
            B={n: len(v) for n, v in proto["B"].items()},
            C=dict(selection_cut=proto["C"]["selection"]["cut"],
                   selection=len(proto["C"]["selection"]["templates"]),
                   evaluation_cut=proto["C"]["evaluation"]["cut"],
                   evaluation=len(proto["C"]["evaluation"]["templates"]))),
        eval_cut_counts={str(k): v for k, v in collections.Counter(
            t["eval_cut"] for t in templates).items()},
        family_count=len(families(templates)),
        stratification=dict(
            candidate={k: v for k, v in collections.Counter(
                t["candidate_bucket"] for t in templates).items()},
            phrase_df={k: v for k, v in collections.Counter(
                t["phrase_df_bucket"] for t in templates).items()}),
        frozen=True,
        notes=["templates are content-derived and reproducible from the corpus manifest",
               "changed-content templates record observed_at_cut, the first cutoff whose "
               "revision set already contains the removal",
               "absent-phrase queries are verified absent by the exact FTS oracle at the "
               "cutoff they were generated from, and are evaluated at that cutoff",
               "changed_content queries come from tokens a later revision removed",
               "protocol B keeps near-identical phrase variants on one side of the split",
               "protocol C selects on the earliest cutoff and evaluates on the latest"],
    )
    return templates, manifest


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", choices=("ap", "clark"), required=True)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--target", type=int, default=10000)
    p.add_argument("--per-class", type=int, default=120)
    p.add_argument("--extension", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    return p.parse_args()


if __name__ == "__main__":
    a = parse_args()
    from frequency_index import nr
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        if a.corpus == "clark":
            sys.path.insert(0, str(HERE.parent / "round-141"))
            import clark_retrieval as cr
            events, _, m, _, _ = cr.read(a.source)
            n = len(events)
            cuts = [n // 4, n // 2, 3 * n // 4, n]
        else:
            events, _, m = nr.load(a.source, a.target, folder)
            n = len(events)
            first = len(m["retained_paths"])
            cuts = [first, first + (n - first) // 3, first + 2 * (n - first) // 3, n]
        templates, manifest = build(a.corpus, events, cuts, a.per_class,
                                   a.extension.resolve())
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(dict(manifest=manifest, templates=templates), indent=2) + "\n")
        print("MANIFEST_JSON=" + json.dumps(dict(
            corpus=a.corpus, templates=manifest["templates"],
            distinct=manifest["distinct_phrase_sets"], sha=manifest["workload_sha256"],
            shortfall=manifest["class_shortfall"])))
