"""R180: the frozen workload must be reproducible, stratified and leak-free."""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))

import workload  # noqa: E402


VOCAB = ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu "
         "nu xi omicron pi rho sigma tau upsilon phi chi psi omega").split()


def corpus(n_docs=60, seed=7):
    """A small synthetic corpus with revisions, built deterministically."""
    import hashlib
    import random
    events = []
    for d in range(n_docs // 2):
        article = "art-%02d" % d
        rng = random.Random(seed * 1000 + d)
        for v in range(2):
            words = [rng.choice(VOCAB) for _ in range(40)]
            # A phrase repeated inside the document, and a phrase the revision removes.
            words[5:8] = ["alpha", "beta", "gamma"]
            words[12:15] = ["alpha", "beta", "gamma"]
            if v == 1:
                words[20:23] = ["delta", "epsilon", "zeta"]
            events.append((article, v, " ".join(words).encode()))
    return events


@pytest.fixture(scope="module")
def built():
    ext = __import__("os").environ["CDG_FTS_EXTENSION"]
    events = corpus()
    cuts = [20, 40, 60]
    templates, manifest = workload.build("ap", events, cuts, 6, ext)
    return templates, manifest


def test_generation_is_deterministic(built):
    templates, _ = built
    events = corpus()
    ext = __import__("os").environ["CDG_FTS_EXTENSION"]
    again, manifest2 = workload.build("ap", events, [20, 40, 60], 6, ext)
    assert workload.manifest_digest(again) == workload.manifest_digest(templates)
    assert manifest2["workload_sha256"] == workload.manifest_digest(templates)


def test_absent_phrases_really_are_absent(built):
    templates, _ = built
    checked = 0
    for cut in (20, 40, 60):
        oracle = workload.Oracle(corpus(), cut)
        for t in templates:
            if t["cls"] != "absent_phrase" or t["eval_cut"] != cut:
                continue
            # Absence is a property of one cutoff, so it is asserted there and the
            # template is evaluated at the same cutoff.
            assert oracle.phrase_df(t["phrases"][0]) == 0
            checked += 1
        oracle.close()
    assert checked, "the synthetic corpus must yield at least one absent phrase"


def test_every_query_is_stratified(built):
    templates, manifest = built
    for t in templates:
        assert t["candidate_bucket"] and t["phrase_df_bucket"] and t["cost_bucket"]
        assert isinstance(t["cand"], int) and isinstance(t["pdf"], int)
    assert manifest["stratification"]["candidate"]
    assert manifest["stratification"]["phrase_df"]


def test_protocol_a_partitions_without_overlap(built):
    templates, _ = built
    proto = workload.protocols(templates, [20, 40, 60])
    seen = {}
    for name, part in proto["A"].items():
        for t in part:
            assert id(t) not in seen, "a template appears in two splits"
            seen[id(t)] = name
    assert len(seen) == len(templates)


def test_protocol_b_keeps_phrase_families_together(built):
    templates, _ = built
    proto = workload.protocols(templates, [20, 40, 60])
    fam = workload.families(templates)
    root_of = {id(t): root for root, members in fam.items() for t in members}
    placement = {}
    for name, part in proto["B"].items():
        for t in part:
            root = root_of[id(t)]
            placement.setdefault(root, set()).add(name)
    assert all(len(v) == 1 for v in placement.values()), \
        "a family was split across train/validation/held-out"


def test_protocol_b_covers_every_template(built):
    templates, _ = built
    proto = workload.protocols(templates, [20, 40, 60])
    assert sum(len(v) for v in proto["B"].values()) == len(templates)


def test_protocol_c_excludes_late_removals_from_selection(built):
    templates, _ = built
    proto = workload.protocols(templates, [20, 40, 60])
    early = proto["C"]["selection"]["templates"]
    assert all(t.get("observed_at_cut", 0) <= 20 for t in early)
    assert len(proto["C"]["evaluation"]["templates"]) == len(templates)


def test_changed_content_is_tracked_when_it_exists(built):
    templates, _ = built
    changed = [t for t in templates if t["cls"] == "changed_content"]
    assert changed, "the synthetic corpus removes a phrase in its second revision"
    for t in changed:
        assert t["observed_at_cut"] >= 1
        assert t["eval_cut"] == t["observed_at_cut"]


@pytest.mark.parametrize("name", ["manifest-ap-10009.json", "manifest-clark-1161.json"])
def test_frozen_manifests_meet_the_size_requirement(name):
    path = HERE.parent / name
    if not path.exists():
        pytest.skip("frozen manifest not present")
    blob = json.loads(path.read_text())
    manifest, templates = blob["manifest"], blob["templates"]
    assert manifest["frozen"] is True
    assert len(templates) >= 1000, "at least 1,000 distinct queries per corpus"
    assert manifest["distinct_phrase_sets"] >= 1000
    assert manifest["workload_sha256"] == workload.manifest_digest(templates)
    assert manifest["class_shortfall"].get("changed_content", 0) in (0, manifest["per_class"])
    for t in templates:
        assert t["cls"] in workload.CLASSES
