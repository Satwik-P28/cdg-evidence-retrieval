"""R183: the coverage objective must reward completion, not participation."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import joint  # noqa: E402


def reqs(*specs):
    return [dict(tids=list(t), weight=w, phrase=[str(x) for x in t]) for t, w in specs]


def test_a_single_token_coverage_is_worth_nothing():
    # The whole point of the round: one token of a three-token phrase covers nothing.
    r = reqs(((1, 2, 3), 100.0))
    assert joint.coverage_objective({1}, r) == 0.0
    assert joint.coverage_objective({1, 2}, r) == 100.0
    assert joint.coverage_objective({1, 3}, r) == 100.0


def test_additive_model_pays_for_participation():
    r = reqs(((1, 2, 3), 90.0))
    value = {}
    for i in r:
        share = i["weight"] / len(i["tids"])
        for t in i["tids"]:
            value[t] = value.get(t, 0) + share
    assert value[1] == value[2] == value[3] == 30.0
    # ... even though no single one of them rejects anything.
    assert joint.coverage_objective({1}, r) == 0.0


def test_joint_greedy_seeds_instead_of_stalling():
    r = reqs(((1, 2), 100.0))
    costs = {1: 10.0, 2: 10.0}
    chosen, spent = joint.joint_coverage(costs, r, budget=100.0)
    assert chosen, "greedy must not stop at an all-zero first step"
    assert spent <= 100.0


def test_joint_greedy_completes_a_phrase_when_it_can_afford_both_tokens():
    r = reqs(((1, 2), 100.0))
    costs = {1: 10.0, 2: 10.0, 3: 1.0}
    chosen, spent = joint.joint_coverage(costs, r, budget=25.0)
    assert {1, 2} <= chosen
    assert joint.coverage_objective(chosen, r) == 100.0
    assert spent <= 25.0


def test_joint_greedy_respects_the_budget():
    r = reqs(((1, 2), 100.0), ((3, 4), 100.0))
    costs = {1: 10.0, 2: 10.0, 3: 10.0, 4: 10.0}
    chosen, spent = joint.joint_coverage(costs, r, budget=15.0)
    assert spent <= 15.0


def test_pairwise_bundles_buy_whole_phrases_only():
    r = reqs(((1, 2, 3), 100.0), ((4, 5, 6), 10.0))
    costs = {1: 10.0, 2: 10.0, 3: 10.0, 4: 1.0, 5: 1.0, 6: 1.0}
    chosen, spent = joint.pairwise_bundles(costs, r, budget=12.0)
    # Only the cheap bundle fits; buying part of the expensive one is not allowed.
    assert chosen == {4, 5, 6}
    assert joint.coverage_objective(chosen, r) == 10.0


def test_exact_gap_measures_greedy_against_the_optimum():
    r = reqs(((1, 2), 100.0), ((3, 4), 90.0), ((1, 3), 50.0))
    costs = {1: 10.0, 2: 10.0, 3: 10.0, 4: 10.0}
    gap = joint.exact_gap(costs, r, budget=20.0)
    assert gap is not None
    assert 0.0 < gap["ratio"] <= 1.0
    assert gap["exact_value"] >= gap["greedy_value"]


def test_exact_gap_reports_no_ratio_when_nothing_is_affordable():
    r = reqs(((1, 2), 100.0))
    costs = {1: 100.0, 2: 100.0}
    gap = joint.exact_gap(costs, r, budget=1.0)
    # Only the empty subset fits, so there is no ratio to report.
    assert gap["exact_value"] == 0
    assert gap["ratio"] is None


def test_local_swap_never_exceeds_the_budget():
    r = reqs(((1, 2), 100.0), ((3, 4), 100.0))
    costs = {1: 10.0, 2: 10.0, 3: 12.0, 4: 12.0}
    seed, _ = joint.joint_coverage(costs, r, budget=20.0)
    chosen, spent = joint.local_swap(costs, r, 20.0, seed)
    assert spent <= 20.0
    assert joint.coverage_objective(chosen, r) >= joint.coverage_objective(seed, r)


def test_independent_df_control_ignores_the_workload():
    r = reqs(((1, 2), 100.0))
    costs = {1: 10.0, 2: 10.0}
    token_df = {1: 1000, 2: 5}
    chosen, spent = joint.independent_df(costs, r, budget=10.0, ids={}, token_df=token_df)
    assert chosen == {1}, "the high-frequency token must win on df per byte"