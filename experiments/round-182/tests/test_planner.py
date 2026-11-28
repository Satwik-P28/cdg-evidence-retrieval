"""R182: the planner must choose a real mode and never invent a cheaper one."""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import planner  # noqa: E402


class FakeDir:
    def __init__(self, n):
        self.n = n


class FakeIndex:
    def __init__(self, covered):
        self.covered = set(covered)

    def directory(self, tid):
        return FakeDir(10) if tid in self.covered else None


class FakeRow:
    def __init__(self, df, size):
        self.df = df
        self.size = size


class FakeDB:
    def __init__(self, postings):
        self.postings = postings

    def execute(self, sql, params=()):
        if "pair_postings" in sql and "df,length" in sql:
            row = self.postings.get(params[0])
            return FakeCursor((row.df, row.size) if row else None)
        if "df FROM pair_postings" in sql:
            row = self.postings.get(params[0])
            return FakeCursor((row.df,) if row else None)
        raise AssertionError(sql)


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeFilters:
    def __init__(self, postings, selective=True, pairs_exist=None):
        self.db = FakeDB(postings)
        self.selective = selective
        self._pairs = postings
        self._exist = bool(postings) if pairs_exist is None else pairs_exist

    def has_pairs(self):
        # A complete index can exist while a particular pair is absent.
        return self._exist


def model(mean_frame=1000.0, rates=None):
    m = object.__new__(planner.CostModel)
    m.rates = rates
    m.mean_frame = mean_frame
    m.mean_position_bytes = 40.0
    return m


def test_plan_without_rejection_or_positions_only_offers_source():
    m = model()
    filters = FakeFilters({})
    mode, estimates = m.plan(["a"], [1], {1, 2, 3}, FakeIndex([]), filters)
    assert mode == "source"
    assert set(estimates) == {"source"}
    assert estimates["source"] == pytest.approx(3000.0)


def test_plan_offers_positions_when_every_token_is_covered():
    m = model()
    mode, estimates = m.plan(["a"], [1], {1, 2}, FakeIndex([1]), FakeFilters({}))
    assert "positions" in estimates


def test_plan_does_not_offer_positions_without_full_coverage():
    m = model()
    code = [1, 2]
    _, estimates = m.plan(["a"], code, {1, 2}, FakeIndex([1]), FakeFilters({}))
    assert "positions" not in estimates


def test_plan_prefers_pairs_when_they_shrink_candidates_cheaply():
    m = model(mean_frame=1000.0)
    pair = planner.rj.pair_key("a", "b")
    filters = FakeFilters({pair: FakeRow(df=2, size=50)})
    mode, estimates = m.plan(["a", "b"], [1, 2], set(range(1, 501)), FakeIndex([]), filters)
    assert mode == "pairs_source"
    assert estimates["pairs_source"] < estimates["source"]


def test_plan_ignores_unindexed_pairs_in_a_selective_index():
    m = model(mean_frame=1000.0)
    filters = FakeFilters({}, selective=True)
    mode, estimates = m.plan(["a", "b"], [1, 2], {1, 2, 3}, FakeIndex([]), filters)
    # Nothing is stored, so nothing can be promised.
    assert mode == "source"


def test_complete_index_with_a_missing_pair_promises_zero_survivors():
    m = model(mean_frame=1000.0)
    filters = FakeFilters({}, selective=False, pairs_exist=True)
    mode, estimates = m.plan(["a", "b"], [1, 2], {1, 2, 3}, FakeIndex([]), filters)
    assert mode == "pairs_source"
    assert estimates["pairs_source"] < estimates["source"]


def test_calibrated_rates_are_used_for_prediction():
    m = model(rates=dict(source_us=100.0, block_us=10.0, pair_byte_us=1.0))
    filters = FakeFilters({})
    mode, estimates = m.plan(["a"], [1], {1, 2}, FakeIndex([]), filters)
    assert mode == "source"
    assert estimates["source"] == pytest.approx(200.0)


def test_after_count_reports_the_smallest_pair_frequency():
    m = model()
    key = planner.rj.pair_key("a", "b")
    filters = FakeFilters({key: FakeRow(df=4, size=10)})
    assert planner._after_count(m, ["a", "b"], filters, 100) == 4


def test_after_count_is_zero_for_a_pair_that_occurs_nowhere():
    m = model()
    filters = FakeFilters({}, selective=False, pairs_exist=True)
    assert planner._after_count(m, ["a", "b"], filters, 100) == 0