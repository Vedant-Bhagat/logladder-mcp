"""reasoning/: risk maths, hypothesis statistics and verdicts, claim extraction and matching."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loglad_mcp.reasoning import claims, hypothesis, risk

# --------------------------------------------------------------------------- risk


def test_percentile_ranks_ties_and_single():
    assert risk.percentile_ranks([7]) == [1.0]
    assert risk.percentile_ranks([1, 2, 3]) == [0.0, 0.5, 1.0]
    assert risk.percentile_ranks([5, 5, 1]) == [0.75, 0.75, 0.0]
    assert risk.percentile_ranks([2, 2]) == [0.5, 0.5]


def test_trend_severity_and_weights():
    assert risk.trend_input(0, 0) == 0.5 and risk.trend_input(0, 10) == 1.0 and risk.trend_input(10, 0) == 0.0
    assert risk.severity("FATAL") == 1.0 and risk.severity("error") == 0.7 and risk.severity("INFO") == 0.1
    w = risk.normalise_weights({"F": 0.6})  # others default, renormalised
    assert abs(sum(w.values()) - 1) < 1e-9 and w["F"] > risk.DEFAULT_WEIGHTS["F"]
    with pytest.raises(ValueError):
        risk.normalise_weights({"F": -1})
    with pytest.raises(ValueError):
        risk.normalise_weights({"Z": 1})


def test_weight_variants_are_ten_and_normalised():
    vs = risk.weight_variants(risk.DEFAULT_WEIGHTS)
    assert len(vs) == 10 and all(abs(sum(v.values()) - 1) < 1e-9 for v in vs)


def _cand(key, ds, eps, scopes, first, level, lines, labelled):
    return risk.Candidate(key, ds, eps, scopes, first, eps - first, level, lines, labelled)


def test_score_all_is_explainable_and_stable():
    cands = [_cand("a", "bgl", 100, 20, 30, "FATAL", 500, 250), _cand("b", "bgl", 50, 10, 25, "ERROR", 100, 0),
             _cand("c", "bgl", 10, 2, 9, "INFO", 10, 0), _cand("d", "bgl", 5, 1, 2, "WARNING", 5, 0)]
    ranked, _w, stab = risk.score_all(cands)
    assert [c.key for c in ranked] == ["a", "b", "c", "d"]
    a = ranked[0]
    assert a.inputs == {"F": 1.0, "S": 1.0, "T": 0.7, "V": 1.0, "L": 0.5}
    assert a.score == round(100 * (0.3 + 0.25 + 0.2 * 0.7 + 0.15 + 0.1 * 0.5), 1)
    assert stab["a"] == 1.0 and stab["d"] == 0.0


def test_percentiles_are_per_dataset():
    cands = [_cand(("bgl", 1), "bgl", 1000, 5, 500, "INFO", 1, 0), _cand(("openstack", 2), "openstack", 3, 1, 1, "INFO", 1, 0)]
    risk.compute_inputs(cands)
    assert cands[0].inputs["F"] == 1.0 and cands[1].inputs["F"] == 1.0

# --------------------------------------------------------------------------- hypothesis


T0 = datetime(2005, 6, 1)


def iv(eid, scope, start_min, dur_min=1):
    s = T0 + timedelta(minutes=start_min)
    return hypothesis.Interval(eid, scope, s, s + timedelta(minutes=dur_min))


def test_support_baseline_lift():
    effects = [iv(1, "A", 100), iv(2, "A", 300), iv(3, "B", 100), iv(4, "B", 500)]
    causes = [iv(10, "A", 95), iv(11, "B", 92, 3)]  # precede effects 1 and 3 within 10 min
    side = hypothesis.one_direction(causes, effects, T0, T0 + timedelta(minutes=600), 600, "midplane")
    assert side.effect_episodes == 4 and side.supported == 2 and side.support == 0.5
    assert side.baseline_windows == 2 * 60 and side.baseline_hits == 2
    assert side.lift == round(0.5 / (2 / 120), 2)
    assert side.examples[0]["episode_id"] == 1 and side.examples[0]["midplane"] == "A"
    assert {c["episode_id"] for c in side.counter_examples} == {2, 4}


def test_cause_after_effect_does_not_count():
    side = hypothesis.one_direction([iv(10, "A", 101)], [iv(1, "A", 100)], T0, T0 + timedelta(hours=10), 600, "midplane")
    assert side.supported == 0


def test_cause_on_other_scope_does_not_count():
    side = hypothesis.one_direction([iv(10, "B", 95)], [iv(1, "A", 100)], T0, T0 + timedelta(hours=10), 600, "midplane")
    assert side.supported == 0 and side.baseline == 0 and side.lift is None


def test_long_cause_overlapping_window_counts():
    side = hypothesis.one_direction([iv(10, "A", 0, 95)], [iv(1, "A", 100)], T0, T0 + timedelta(hours=10), 600, "midplane")
    assert side.supported == 1


def _side(n, support, lift):
    return hypothesis.Side(n, 0, 0, 0, support, None, lift, [], [])


@pytest.mark.parametrize("fwd,rev,expected", [
    (_side(4, 0.9, 10), _side(4, 0, 0), "insufficient_data"),
    (_side(10, 0.6, 3.0), _side(10, 0, 1.0), "strong"),
    (_side(10, 0.6, 3.0), _side(10, 0, 4.0), "moderate"),  # reverse stronger -> not strong
    (_side(10, 0.3, 1.5), _side(10, 0, 0), "moderate"),
    (_side(10, 0.2, 1.2), _side(10, 0, 0), "weak"),
    (_side(10, 0.2, 0.9), _side(10, 0, 0), "none"),
    (_side(10, 0.0, None), _side(10, 0, 0), "none"),
])
def test_verdict_thresholds(fwd, rev, expected):
    assert hypothesis.verdict(fwd, rev) == expected

# --------------------------------------------------------------------------- claims


RECEIPTS = {
    "R-0005": {"data": {"items": [{"episodes": 210, "lines": 1284, "change_pct": 121.1, "share": 0.5625,
                                   "first_ts": "2005-06-14T09:12:03.512345"}]},
               "scope": {"from": "2005-06-01", "to": "2005-06-30"}, "total_matches": 57, "returned": 2},
    "R-0007": {"data": {"window_s": 600, "forward": {"lift": 13.6}}, "scope": {}, "total_matches": 90, "returned": 3},
}


def check(draft):
    return claims.check(draft, RECEIPTS.get)


def by_text(result):
    return {c["text"]: c for c in result["claims"]}


def test_numbers_percentages_and_dates_backed():
    r = check("- 210 episodes and 1,284 lines, up 121% since 2005-06-01, first at 09:12:03 [R-0005]\n"
              "- 56.25% of episodes [R-0005]\n- Within 10 minutes, lift 13.6 [R-0007]")
    c = by_text(r)
    assert all(x["status"] == "backed" for x in r["claims"]), r["claims"]
    assert c["121%"]["note"] == "rounded from 121.1"
    assert "10 minutes" in c and r["ok"] is True


def test_mismatched_unbacked_and_missing_receipt():
    r = check("- 211 episodes [R-0005]\n- 300 nodes failed.\n- 5 things [R-0999]")
    c = by_text(r)
    assert c["211 episodes"]["status"] == "mismatched" and "closest: 210" in c["211 episodes"]["note"]
    assert c["300 nodes"]["status"] == "unbacked"
    assert c["5 things"]["status"] == "mismatched" and "R-0999" in c["5 things"]["note"]
    assert r["ok"] is False


def test_structural_numbers_ignored():
    r = check("1. Look at the top 5 problems and the first 3 hours.\n- Template `42` on R23-M0, see [R-0005].\n"
              "### Next step\n2) Check nova-api 2xx codes")
    assert r["claims"] == []


def test_list_positions_params_and_window_length_backed():
    rec = {"R-0009": {"data": {"risks": [{"score": 92.1}]}, "params": {"top_n": 8, "dataset": "bgl"},
                      "scope": {"from": "2005-12-05T08:00:05", "to": "2006-01-04T08:00:05"},
                      "total_matches": 348, "returned": 5}}
    r = claims.check("- HPC owns ranks 1, 2, 4 and 5, and #3 scores 92.1 [R-0009].\n"
                     "- Over the last 30 days, the 8 largest problems [R-0009].\n- 31 days [R-0009]", rec.get)
    c = by_text(r)
    assert set(c) == {"92.1", "30 days", "8 largest", "31 days"}, c
    assert c["30 days"]["status"] == c["8 largest"]["status"] == "backed"
    assert c["31 days"]["status"] == "mismatched"


def test_causal_and_impact_words_by_section():
    r = check("### Observed\n- Kernel panics happened because of parity errors [R-0005].\n"
              "### Hypotheses\n- Parity errors may have caused it [R-0007].\n"
              "### Unknowns\n- Downtime and revenue loss.\n### Next step\n- Reduce outage risk.")
    flagged = [(c["kind"], c["text"]) for c in r["claims"] if c["status"] == "flagged"]
    assert flagged == [("causal_word", "because"), ("impact_word", "outage")]


def test_bold_and_colon_headings():
    units = claims.split_units("**Observed:** 210 episodes [R-0005]\nUnknowns: costs\nScope\n- x")
    assert [(u.section, u.text) for u in units] == [("observed", "210 episodes [R-0005]"), ("unknowns", "costs"),
                                                    ("scope", "x")]
    assert units[0].receipt_ids == ["R-0005"]


def test_sentences_split_but_bullets_kept():
    units = claims.split_units("First 210 episodes [R-0005]. Then 99 more.\n- One. Two [R-0007].")
    assert [u.text for u in units] == ["First 210 episodes [R-0005].", "Then 99 more.", "One. Two [R-0007]."]
