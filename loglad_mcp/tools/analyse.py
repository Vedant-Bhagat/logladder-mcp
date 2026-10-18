"""recurring_problems and rank_risks (analyse, rungs 2–4). Inputs from `episodes`; maths in reasoning/risk.py."""
from typing import Annotated, Literal

from pydantic import Field

from loglad_mcp.core.envelope import make_scope
from loglad_mcp.core.limits import RISKS_DEFAULT, RISKS_MAX, TOP_N_DEFAULT, TOP_N_MAX, clamp
from loglad_mcp.core.timeparse import dataset_span
from loglad_mcp.reasoning import risk
from loglad_mcp.tools._base import (
    LABEL,
    LEVEL_RANK,
    Role,
    Sql,
    ToolResult,
    datasets_of,
    fmt_int,
    gap_label,
    level_from_rank,
    level_rank_sql,
    placeholders,
    short,
    template_texts,
    to_int,
    tool_call,
    when_txt,
    windows_for,
)

ROLE_FIELD = Field(description="Who the answer is for; pass it on every call.")
RECENT_DAYS = 30
HISTORY_CAVEAT = ("The datasets are historical (BGL 2005–06, OpenStack 2017): 'last 30 days' means the last 30 days "
                  "of each dataset's own span, not of today.")


def _os_instances(q: Sql, tids: list[int], start, end) -> dict[int, int]:
    """OpenStack spread = distinct instances per template in the window (episodes are per service)."""
    if not tids:
        return {}
    rows = q(f"SELECT template_id, count(DISTINCT instance_id) AS n FROM os_events WHERE ts >= %s AND ts < %s "
             f"AND template_id IN {placeholders(tids)} GROUP BY template_id", [start, end, *tids])
    return {to_int(r["template_id"]): to_int(r["n"]) for r in rows}


def _template_stats(q: Sql, ds: str, start, end, team: str | None, min_rank: int | None, split=None) -> list[dict]:
    where = ["dataset = %s", "start_ts >= %s", "start_ts < %s"]
    params: list = [ds, start, end]
    if team:
        where.append("team = %s")
        params.append(team)
    if min_rank:
        where.append(f"{level_rank_sql('max_level')} >= %s")
        params.append(min_rank)
    first = ""
    if split is not None:
        first = ", sum(CASE WHEN start_ts < %s THEN 1 ELSE 0 END) AS first_half"
        params = [split, *params]
    return q(f"SELECT template_id, count(*) AS episodes, sum(line_count) AS lines, "
             f"count(DISTINCT scope_key) AS scopes, max({level_rank_sql('max_level')}) AS lvl_rank, "
             f"sum(labelled_lines) AS labelled, mode(team) AS team, mode(component) AS component{first} "
             f"FROM episodes WHERE {' AND '.join(where)} GROUP BY template_id "
             f"ORDER BY episodes DESC, lines DESC, template_id", params)


@tool_call("recurring_problems")
def recurring_problems(
    dataset: Annotated[Literal["bgl", "openstack", "both"], Field(description="Which dataset(s).")] = "both",
    start: Annotated[str | None, Field(description="Inclusive ISO start. Default: 30 days before end.")] = None,
    end: Annotated[str | None, Field(description="ISO end; date-only includes that day. Default: end of each "
                                                 "dataset.")] = None,
    team: Annotated[str | None, Field(description="Only this team (see loglad://ownership).")] = None,
    min_level: Annotated[str | None, Field(description="Only episodes at or above this level, e.g. ERROR.")] = None,
    top_n: Annotated[int, Field(description=f"Problems to return, default {TOP_N_DEFAULT}, max {TOP_N_MAX}.")] = TOP_N_DEFAULT,
    compare_to_previous: Annotated[bool, Field(description="Compare with the same-length period just before "
                                                           "(default true).")] = True,
    role: Annotated[Role, ROLE_FIELD] = "unknown",
) -> ToolResult:
    datasets = datasets_of(dataset)
    caveats: list[str] = []
    top_n = clamp(int(top_n), 1, TOP_N_MAX, caveats, "top_n")
    min_rank = None
    if min_level:
        if min_level.strip().upper() not in LEVEL_RANK:
            raise ValueError(f"min_level must be one of {', '.join(LEVEL_RANK)}.")
        min_rank = LEVEL_RANK[min_level.strip().upper()]
    q = Sql()
    wins, frm, to, wcav = windows_for(q, datasets, start, end, recent_days=RECENT_DAYS)
    caveats += wcav
    if not start:
        caveats.append(HISTORY_CAVEAT)
    items, n_templates = [], 0
    for ds in datasets:
        w = wins[ds]
        rows = _template_stats(q, ds, w.start, w.end, team, min_rank)
        n_templates += len(rows)
        for r in rows[:top_n]:
            items.append({"ds": ds, "w": w, "r": r})
    items.sort(key=lambda i: (-to_int(i["r"]["episodes"]), -to_int(i["r"]["lines"]), to_int(i["r"]["template_id"])))
    items = items[:top_n]
    texts = template_texts(q, [to_int(i["r"]["template_id"]) for i in items])
    prev: dict[tuple, int] = {}
    if compare_to_previous:
        for ds in datasets:
            tids = [to_int(i["r"]["template_id"]) for i in items if i["ds"] == ds]
            if not tids:
                continue
            w = wins[ds]
            p0 = w.start - (w.end - w.start)
            lo, _ = dataset_span(q, ds)
            if p0 < lo:
                caveats.append(f"{ds}: the previous period starts before the data does ({str(lo)[:10]}), so "
                               f"previous counts may be low.")
            where, params = "dataset = %s AND start_ts >= %s AND start_ts < %s", [ds, p0, w.start]
            if team:
                where += " AND team = %s"
                params.append(team)
            if min_rank:
                where += f" AND {level_rank_sql('max_level')} >= %s"
                params.append(min_rank)
            for r in q(f"SELECT template_id, count(*) AS n FROM episodes WHERE {where} AND template_id IN "
                       f"{placeholders(tids)} GROUP BY template_id", params + tids):
                prev[(ds, to_int(r["template_id"]))] = to_int(r["n"])
    os_inst = {}
    if "openstack" in datasets:
        tids = [to_int(i["r"]["template_id"]) for i in items if i["ds"] == "openstack"]
        os_inst = _os_instances(q, tids, wins["openstack"].start, wins["openstack"].end)
    out = []
    for rank_no, i in enumerate(items, 1):
        r, ds = i["r"], i["ds"]
        tid = to_int(r["template_id"])
        eps = to_int(r["episodes"])
        p = prev.get((ds, tid), 0) if compare_to_previous else None
        out.append({
            "rank": rank_no, "template_id": tid,
            "template_text": (texts.get(tid) or {}).get("template_text") or f"template {tid}",
            "dataset": ds, "component": r["component"], "team": r["team"] or "Unowned",
            "episodes": eps, "lines": to_int(r["lines"]),
            "distinct_scopes": os_inst.get(tid, 0) if ds == "openstack" else to_int(r["scopes"]),
            "max_level": level_from_rank(r["lvl_rank"], ds),
            "prev_episodes": p,
            "change_pct": None if not compare_to_previous or not p else round((eps - p) / p * 100, 1),
        })
    truncated = n_templates > len(out)
    if truncated:
        caveats.append(f"Showing top {len(out)} of {n_templates} templates with episodes in this window.")
    caveats.append("distinct_scopes = distinct midplanes (BGL) or distinct instances (OpenStack).")
    shown = {k: v for k, v in (("team", team), ("min_level", min_level and min_level.upper())) if v}
    scope = make_scope(dataset, frm, to, shown, unit="episodes", episode_gap=gap_label(datasets), group_by="template")
    ds_txt = " + ".join(LABEL[d] for d in datasets)
    when = when_txt(frm, to, "over each dataset's own window" if start or end else
                    "over the last 30 days of each dataset")
    if out:
        t = out[0]
        chg = f" ({t['change_pct']:+.1f}% vs previous period)" if t["change_pct"] is not None else ""
        lead = f"; #1 '{short(t['template_text'], 70)}' with {fmt_int(t['episodes'])} episodes{chg}"
    else:
        lead = "; no episodes in this window"
    summary = f"Top {len(out)} recurring {ds_txt} problems by episodes {when}{lead}."
    return ToolResult(summary, scope, {"items": out}, n_templates, len(out), truncated, q.statements, caveats)


@tool_call("rank_risks")
def rank_risks(
    dataset: Annotated[Literal["bgl", "openstack", "both"], Field(description="Which dataset(s).")] = "both",
    start: Annotated[str | None, Field(description="Inclusive ISO start. Default: 30 days before end.")] = None,
    end: Annotated[str | None, Field(description="ISO end. Default: end of each dataset.")] = None,
    top_n: Annotated[int, Field(description=f"Risks to return, default {RISKS_DEFAULT}, max {RISKS_MAX}.")] = RISKS_DEFAULT,
    min_episodes: Annotated[int, Field(description="Ignore templates with fewer episodes (default 2).")] = 2,
    weights: Annotated[dict[str, float] | None, Field(
        description="Optional weights for F (frequency), S (spread), T (trend), V (severity), L (labelled share); "
                    "default F .30 S .25 T .20 V .15 L .10, renormalised to sum 1.")] = None,
    role: Annotated[Role, ROLE_FIELD] = "unknown",
) -> ToolResult:
    datasets = datasets_of(dataset)
    caveats: list[str] = []
    top_n = clamp(int(top_n), 1, RISKS_MAX, caveats, "top_n")
    min_episodes = max(1, int(min_episodes))
    risk.normalise_weights(weights)  # validate before touching the database
    q = Sql()
    wins, frm, to, wcav = windows_for(q, datasets, start, end, recent_days=RECENT_DAYS)
    caveats += wcav
    if not start:
        caveats.append(HISTORY_CAVEAT)
    cands, meta = [], {}
    for ds in datasets:
        w = wins[ds]
        mid = w.start + (w.end - w.start) / 2
        rows = [r for r in _template_stats(q, ds, w.start, w.end, None, None, split=mid)
                if to_int(r["episodes"]) >= min_episodes]
        inst = _os_instances(q, [to_int(r["template_id"]) for r in rows], w.start, w.end) if ds == "openstack" else {}
        for r in rows:
            tid, eps = to_int(r["template_id"]), to_int(r["episodes"])
            first = to_int(r["first_half"])
            c = risk.Candidate(key=(ds, tid), dataset=ds, episodes=eps,
                               distinct_scopes=inst.get(tid, 0) if ds == "openstack" else to_int(r["scopes"]),
                               first_half=first, second_half=eps - first,
                               max_level=level_from_rank(r["lvl_rank"], ds), lines=to_int(r["lines"]),
                               labelled_lines=to_int(r["labelled"]))
            cands.append(c)
            meta[c.key] = {"team": r["team"] or "Unowned", "component": r["component"]}
    if not cands:
        ranked, w_norm, stab = [], risk.normalise_weights(weights), {}
    else:
        ranked, w_norm, stab = risk.score_all(cands, weights)
    top = ranked[:top_n]
    texts = template_texts(q, [c.key[1] for c in top])
    items = []
    for i, c in enumerate(top, 1):
        tid = c.key[1]
        text = (texts.get(tid) or {}).get("template_text") or f"template {tid}"
        comp = meta[c.key]["component"]
        items.append({
            "rank": i, "template_id": tid, "title": short(f"{text} ({comp})" if comp else text, 100),
            "dataset": c.dataset, "team": meta[c.key]["team"], "score": c.score, "inputs": c.inputs,
            "raw": {"episodes": c.episodes, "distinct_scopes": c.distinct_scopes, "first_half_episodes": c.first_half,
                    "second_half_episodes": c.second_half, "max_level": c.max_level,
                    "labelled_share": c.inputs["L"]},
            "stability_top3": round(stab.get(c.key, 0.0), 2),
        })
    caveats.append("Weights are a policy choice, not a measurement. Score says nothing about business impact.")
    caveats.append(f"{len(cands)} candidate templates with at least {min_episodes} episodes; F and S are percentile "
                   f"ranks among candidates of the same dataset.")
    if len(datasets) > 1:
        caveats.append("dataset=both: percentiles are computed per dataset, then items are merged by score.")
    data = {"weights": {k: round(v, 4) for k, v in w_norm.items()}, "items": items}
    scope = make_scope(dataset, frm, to, {}, unit="episodes", episode_gap=gap_label(datasets), group_by="template")
    when = when_txt(frm, to, "over each dataset's own window" if start or end else
                    "over the last 30 days of each dataset")
    if items:
        t = items[0]
        lead = (f"; top: '{short(t['title'], 70)}' ({t['dataset']}, {t['team']}) score {t['score']:g}, in the top 3 "
                f"for {t['stability_top3'] * 100:.0f}% of weight variants")
    else:
        lead = "; no candidates"
    summary = f"{len(items)} of {len(cands)} candidate problems scored {when}{lead}."
    return ToolResult(summary, scope, data, len(cands), len(items), len(cands) > len(items), q.statements, caveats)
