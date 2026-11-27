"""R179: the repair analysis must be mechanically checkable."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import repair  # noqa: E402


def rec(name, size, p95, **kw):
    r = dict(round="rX", corpus="ap", arm=name, physical_bytes=size, score_error=0.0,
             rank_checks=10, latency=dict(median_us=p95 / 2, p95_us=p95, p99_us=p95 * 1.1,
                                          max_us=p95 * 1.5, samples=10), work={})
    r.update(kw)
    return r


def test_pareto_keeps_only_undominated_arms():
    arms = [rec("cheap_slow", 100, 50), rec("mid", 150, 40), rec("expensive_fast", 200, 10),
            rec("bad", 300, 60)]
    front = repair.pareto(arms)
    names = [a["arm"] for a in front]
    assert "bad" not in names, "an arm beaten on both axes must not be on the frontier"
    assert names == ["cheap_slow", "mid", "expensive_fast"]


def test_pareto_keeps_ties():
    front = repair.pareto([rec("a", 100, 10), rec("b", 100, 10)])
    assert {a["arm"] for a in front} == {"a", "b"}


def test_pareto_skips_records_without_measurements():
    unmeasured = dict(round="rX", corpus="ap", arm="missing", physical_bytes=None,
                      latency=dict(median_us=None, p95_us=None, p99_us=None, max_us=None,
                                   samples=0), work={})
    front = repair.pareto([rec("a", 100, 10), unmeasured])
    assert [a["arm"] for a in front] == ["a"]


def test_relation_calls_lower_bytes_and_lower_latency_dominance():
    r = repair.relation(rec("a", 100, 10), rec("b", 200, 20))
    assert r["kind"] == "dominance" and r["winner"] == "a"


def test_relation_calls_mixed_axes_a_trade_off():
    r = repair.relation(rec("small_slow", 100, 50), rec("big_fast", 200, 10))
    assert r["kind"] == "trade-off"
    assert r["smaller"] == "small_slow" and r["faster"] == "big_fast"


def test_bytes_per_query_divides_by_rank_checks_not_latency():
    # The R174 bug: a latency was stored under a byte name.  The corrected value is
    # logical storage activation per query, and it names the counters it used.
    work = {"storage_bytes_activated": 40_000}
    assert repair.per_query_bytes(work, 100) == dict(bytes=400.0, basis="storage_bytes_activated")
    assert repair.per_query_bytes(work, 0) == dict(bytes=None, basis=None)
    assert repair.per_query_bytes({}, 10) == dict(bytes=None, basis=None)
    # R174's stored counters have no positional block activation; the fallback says so.
    fallback = repair.per_query_bytes({"posting_bytes": 100, "source_activated_bytes": 300}, 10)
    assert fallback == dict(bytes=40.0, basis="posting_bytes+source_activated_bytes")


def test_budget_correction_separates_estimate_from_measurement():
    raw = dict(manifest_sha256=repair.EXPECTED["ap"], query_plan_sha256="x", revisions=10,
               cutoffs=[1, 10], sweep=dict(frequency_archive_bytes=1_000, split_sizes={"train": 6}),
               policies={"arm": dict(sqlite_bytes=1_500, rank_checks=2,
                                     budget_bytes=1_100, budget_fraction=1.1,
                                     selected_payload_bytes=800, selected_directory_bytes=200,
                                     query=dict(median_us=5.0, p95_us=9.0, p99_us=10.0, max_us=11.0, samples=2),
                                     work={"storage_bytes_activated": 300})})
    arms = repair.normalise(raw, "r174", "ap", "policies")
    b = arms[0]["budget_correction"]
    assert b["estimated_budget_bytes"] == 1_100
    assert b["selected_payload_plus_directory_bytes"] == 1_000
    assert b["measured_archive_increment_bytes"] == 500
    assert b["structural_overhead_bytes"] == -500  # measured growth below the estimate
    assert arms[0]["bytes_per_query"] == 150.0


def test_unverified_manifest_is_rejected(monkeypatch, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(dict(manifest_sha256="0" * 64, policies={"a": dict(sqlite_bytes=1)})))
    monkeypatch.setattr(repair, "SOURCES", [("r173", "ap", str(bad), "policies")])
    monkeypatch.setattr(repair, "ROOT", tmp_path)
    records, provenance = repair.load_results()
    assert records == []
    assert provenance[0]["manifest_verified"] is False


def test_committed_results_rebuild_the_tables():
    result = repair.run()
    assert result["provenance"], "at least one stored result file must be readable"
    assert all(p["manifest_verified"] for p in result["provenance"]
               if p["corpus"] in repair.EXPECTED)
    # P99 and max are reported for every arm that has a latency block.
    for r in result["heldout_table"]:
        if r["heldout_p95_us"] is not None:
            assert r["heldout_p99_us"] is not None and r["heldout_max_us"] is not None
    assert (HERE.parents[2] / "research/rounds/round-179/tables.md").exists()
