"""count_by and trend (aggregate, rungs 2–3). Aggregates run on base tables, never on the indexes."""
from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from pydantic import Field

from loglad_mcp.core.envelope import make_scope
from loglad_mcp.core.limits import TOP_N_DEFAULT, TOP_N_MAX, TREND_SERIES_DEFAULT, TREND_SERIES_MAX, clamp
from loglad_mcp.core.timeparse import iso_day
from loglad_mcp.tools._base import (
    ERROR_LEVELS,
    EVENTS,
    LABEL,
    Role,
    Sql,
    ToolResult,
    check_dataset,
    datasets_of,
    fmt_int,
    gap_label,
    num,
    ownership,
    short,
    template_texts,
    to_int,
    tool_call,
    when_txt,
    windows_for,
)

ROLE_FIELD = Field(description="Who the answer is for; pass it on every call.")
COMPONENT_COL = {"bgl": "component", "openstack": "service"}

# group_by -> SQL expression, per unit and dataset (spec 02 §4.5)
EPISODE_GROUP = {"dataset": "dataset", "team": "team", "level": "max_level", "template": "template_id",
                 "component": "component", "midplane": "scope_key", "service": "component"}
LINE_GROUP = {
    "bgl": {"dataset": "'bgl'", "team": "coalesce(o.team, 'Unowned')", "level": "e.level",
            "template": "e.template_id", "component": "e.component", "midplane": "e.midplane",
            "alert_category": "e.alert_category"},
    "openstack": {"dataset": "'openstack'", "team": "coalesce(o.team, 'Unowned')", "level": "e.level",
                  "template": "e.template_id", "service": "e.service", "http_status": "e.http_status"},
}
VALID = {
    ("bgl", "lines"): ("dataset", "team", "level", "template", "component", "midplane", "alert_category"),
    ("bgl", "episodes"): ("dataset", "team", "level", "template", "component", "midplane"),
    ("openstack", "lines"): ("dataset", "team", "level", "template", "service", "http_status"),
    ("openstack", "episodes"): ("dataset", "team", "level", "template", "service"),
}


def _valid_groups(datasets: list[str], unit: str) -> tuple[str, ...]:
    sets = [VALID[(d, unit)] for d in datasets]
    return tuple(g for g in sets[0] if all(g in s for s in sets))


def _source(ds: str, unit: str, needs_team: bool) -> tuple[str, str]:
    """(FROM clause, time column) for one dataset and unit."""
    if unit == "episodes":
        return "episodes", "start_ts"
    join = (f" LEFT JOIN ownership o ON o.dataset = '{ds}' AND o.component = e.{COMPONENT_COL[ds]}"
            if needs_team else "")
    return f"{EVENTS[ds]} e{join}", "e.ts"


def _filters(ds: str, unit: str, level, component, team, template_id=None) -> tuple[list[str], list, dict]:
    where, params, shown = [], [], {}
    if unit == "episodes":
        where.append("dataset = %s")
        params.append(ds)
        cols = {"level": "max_level", "component": "component", "team": "team", "template_id": "template_id"}
    else:
        cols = {"level": "e.level", "component": f"e.{COMPONENT_COL[ds]}", "team": "coalesce(o.team, 'Unowned')",
                "template_id": "e.template_id"}
    for name, value in (("level", level), ("component", component), ("team", team), ("template_id", template_id)):
        if value is None or value == "":
            continue
        if name == "level" or name == "component" and ds == "bgl":
            value = str(value).strip().upper()
        elif name == "template_id":
            value = int(value)
        where.append(f"{cols[name]} = %s")
        params.append(value)
        shown[name] = value
    return where, params, shown


@tool_call("count_by")
def count_by(
    dataset: Annotated[Literal["bgl", "openstack", "both"], Field(description="Which dataset(s).")],
    group_by: Annotated[Literal["dataset", "team", "level", "template", "component", "midplane", "alert_category",
                                "service", "http_status"], Field(
        description="BGL: component|midplane|alert_category; OpenStack: service|http_status; both: "
                    "dataset|team|level|template. alert_category and http_status need unit='lines'.")],
    unit: Annotated[Literal["episodes", "lines"], Field(
        description="episodes (default; bursts count once) or raw lines.")] = "episodes",
    start: Annotated[str | None, Field(description="Inclusive ISO start; default dataset start.")] = None,
    end: Annotated[str | None, Field(description="ISO end; date-only includes that day; default dataset end.")] = None,
    level: Annotated[str | None, Field(description="Only this level (episodes: the episode's max level).")] = None,
    component: Annotated[str | None, Field(description="Only this BGL component / OpenStack service.")] = None,
    team: Annotated[str | None, Field(description="Only this team (see loglad://ownership).")] = None,
    top_n: Annotated[int, Field(description=f"Rows to return, default {TOP_N_DEFAULT}, max {TOP_N_MAX}; the rest "
                                            f"is folded into `other`.")] = TOP_N_DEFAULT,
    role: Annotated[Role, ROLE_FIELD] = "unknown",
) -> ToolResult:
    datasets = datasets_of(dataset)
    if unit not in ("episodes", "lines"):
        raise ValueError("unit must be episodes or lines.")
    valid = _valid_groups(datasets, unit)
    if group_by not in valid:
        raise ValueError(f"group_by '{group_by}' is not available for dataset={dataset}, unit={unit}. "
                         f"Valid options: {', '.join(valid)}.")
    caveats: list[str] = []
    top_n = clamp(int(top_n), 1, TOP_N_MAX, caveats, "top_n")
    q = Sql()
    wins, frm, to, wcav = windows_for(q, datasets, start, end)
    caveats += wcav
    needs_team = group_by == "team" or bool(team)
    owners = ownership(q) if group_by in ("component", "service", "template") else {}
    merged: dict = {}
    shown_filters: dict = {}
    for ds in datasets:
        src, tcol = _source(ds, unit, needs_team)
        expr = EPISODE_GROUP[group_by] if unit == "episodes" else LINE_GROUP[ds][group_by]
        where, params, shown_filters = _filters(ds, unit, level, component, team)
        where += [f"{tcol} >= %s", f"{tcol} < %s"]
        params += [wins[ds].start, wins[ds].end]
        rows = q(f"SELECT {expr} AS k, count(*) AS n FROM {src} WHERE {' AND '.join(where)} "
                 f"GROUP BY 1 ORDER BY n DESC", params)
        for r in rows:
            k = r["k"]
            k = to_int(k) if group_by in ("template", "http_status") and k is not None else k
            merge_key = k if (len(datasets) == 1 or group_by in ("dataset", "team")) else (ds, k)
            slot = merged.setdefault(merge_key, {"key": k, "ds": ds, "count": 0})
            slot["count"] += to_int(r["n"])
    groups = sorted(merged.values(), key=lambda g: (-g["count"], str(g["key"])))
    total = sum(g["count"] for g in groups)
    top, rest = groups[:top_n], groups[top_n:]
    texts = template_texts(q, [g["key"] for g in top]) if group_by == "template" else {}
    rows_out = []
    for g in top:
        k, ds = g["key"], g["ds"]
        label = "(none)" if k is None else str(k)
        team_of = None
        if group_by == "template" and k is not None:
            t = texts.get(k) or {}
            label = f"#{k} {short(t.get('template_text') or '', 70)}".strip()
            team_of = owners.get((ds, t.get("component")), "Unowned")
        elif group_by in ("component", "service"):
            team_of = owners.get((ds, k), "Unowned")
        elif group_by == "team":
            team_of = k
        if len(datasets) > 1 and group_by not in ("dataset", "team"):
            label = f"{ds} · {label}"
        row = {"key": k, "label": label, "count": g["count"], "share": round(g["count"] / total, 4) if total else 0}
        if team_of is not None:
            row["team"] = team_of
        rows_out.append(row)
    other = None
    if rest:
        n = sum(g["count"] for g in rest)
        other = {"count": n, "share": round(n / total, 4) if total else 0, "groups": len(rest)}
    if unit == "episodes":
        caveats.append(f"Episodes, not lines: repeats of one template in one scope less than "
                       f"{gap_label(datasets)} apart count once.")
    data = {"group_by": group_by, "unit": unit, "rows": rows_out, "other": other, "total": total}
    scope = make_scope(dataset, frm, to, shown_filters, unit=unit,
                       episode_gap=gap_label(datasets) if unit == "episodes" else None, group_by=group_by)
    ds_txt = " + ".join(LABEL[d] for d in datasets)
    when = when_txt(frm, to, "over each dataset's own window")
    top_txt = (f"; top: {rows_out[0]['label']} {fmt_int(rows_out[0]['count'])} "
               f"({rows_out[0]['share'] * 100:.1f}%)") if rows_out else ""
    summary = (f"{ds_txt} {unit} {when} grouped by {group_by}: {len(groups)} groups, {fmt_int(total)} {unit} "
               f"in total{top_txt}.")
    return ToolResult(summary, scope, data, total, len(rows_out), other is not None, q.statements, caveats)


# --------------------------------------------------------------------------- trend

def buckets(start: datetime, end: datetime, bucket: str) -> list[date]:
    """Bucket starts covering [start, end); weeks start on Monday."""
    d = start.date()
    if bucket == "week":
        d -= timedelta(days=d.weekday())
    step = timedelta(days=7 if bucket == "week" else 1)
    out = []
    while datetime.combine(d, datetime.min.time()) < end:
        out.append(d)
        d += step
    return out


def series_change(values: list[float | None], use_mean: bool) -> dict:
    """first/second half (sum, or mean for rates), least-squares slope per bucket, last vs previous in %."""
    n = len(values)
    h = n // 2
    first, second = values[:h], values[n - h:]

    def agg(vs):
        vs = [v for v in vs if v is not None]
        if not vs:
            return 0.0
        return sum(vs) / len(vs) if use_mean else float(sum(vs))

    pts = [(i, v) for i, v in enumerate(values) if v is not None]
    slope = 0.0
    if len(pts) >= 2:
        mx = sum(i for i, _ in pts) / len(pts)
        my = sum(v for _, v in pts) / len(pts)
        den = sum((i - mx) ** 2 for i, _ in pts)
        slope = sum((i - mx) * (v - my) for i, v in pts) / den if den else 0.0
    last_pct = None
    if n >= 2 and values[-1] is not None and values[-2] not in (None, 0):
        last_pct = round((values[-1] - values[-2]) / values[-2] * 100, 1)
    nd = 4 if use_mean else 2
    return {"first_half": round(agg(first), nd), "second_half": round(agg(second), nd),
            "slope_per_bucket": round(slope, nd), "last_vs_prev_pct": last_pct}


UNIT_LABEL = {"lines": "lines per {b}", "episodes": "episodes per {b}", "error_rate": "error lines / all lines per {b}",
              "latency_p95": "p95 latency (s) per {b}"}


@tool_call("trend")
def trend(
    dataset: Annotated[Literal["bgl", "openstack"], Field(description="Which dataset.")],
    metric: Annotated[Literal["lines", "episodes", "error_rate", "latency_p95"], Field(
        description="lines, episodes, error_rate (error lines / all lines) or latency_p95 (OpenStack only).")],
    bucket: Annotated[Literal["day", "week"], Field(description="Bucket size; weeks start Monday.")] = "week",
    group_by: Annotated[Literal["none", "team", "component", "service", "level", "template"], Field(
        description="Split into series by this; component = BGL component / OpenStack service.")] = "none",
    start: Annotated[str | None, Field(description="Inclusive ISO start; default dataset start.")] = None,
    end: Annotated[str | None, Field(description="ISO end; date-only includes that day; default dataset end.")] = None,
    level: Annotated[str | None, Field(description="Only this level.")] = None,
    component: Annotated[str | None, Field(description="Only this BGL component / OpenStack service.")] = None,
    team: Annotated[str | None, Field(description="Only this team.")] = None,
    template_id: Annotated[int | None, Field(description="Only this template.")] = None,
    top_series: Annotated[int, Field(description=f"Series to keep (largest by volume), default "
                                                 f"{TREND_SERIES_DEFAULT}, max {TREND_SERIES_MAX}.")] = TREND_SERIES_DEFAULT,
    role: Annotated[Role, ROLE_FIELD] = "unknown",
) -> ToolResult:
    ds = check_dataset(dataset)
    if metric == "latency_p95" and ds != "openstack":
        raise ValueError("latency_p95 exists only for openstack (BGL lines have no latency).")
    if bucket not in ("day", "week"):
        raise ValueError("bucket must be day or week.")
    if group_by == "service" and ds == "bgl":
        raise ValueError("group_by='service' is OpenStack only; for BGL use component.")
    if group_by == "component" and ds == "openstack":
        group_by_eff = "service"
    else:
        group_by_eff = group_by
    caveats: list[str] = []
    top_series = clamp(int(top_series), 1, TREND_SERIES_MAX, caveats, "top_series")
    unit = "episodes" if metric == "episodes" else "lines"
    q = Sql()
    wins, frm, to, _ = windows_for(q, [ds], start, end)
    w = wins[ds]
    needs_team = group_by_eff == "team" or bool(team)
    src, tcol = _source(ds, unit, needs_team)
    where, params, shown = _filters(ds, unit, level, component, team, template_id)
    where += [f"{tcol} >= %s", f"{tcol} < %s"]
    params += [w.start, w.end]
    if metric == "latency_p95":
        where.append("e.latency_s IS NOT NULL")
        value = "quantile_cont(e.latency_s, 0.95)"
    elif metric == "error_rate":
        errs = ", ".join(f"'{lv}'" for lv in ERROR_LEVELS[ds])
        value = f"sum(CASE WHEN e.level IN ({errs}) THEN 1 ELSE 0 END)"
    else:
        value = "count(*)"
    g_sql = ""
    if group_by_eff != "none":
        expr = EPISODE_GROUP[group_by_eff] if unit == "episodes" else LINE_GROUP[ds][group_by_eff]
        g_sql = f", {expr} AS g"
    rows = q(f"SELECT date_trunc('{bucket}', {tcol}) AS t{g_sql}, {value} AS v, count(*) AS w FROM {src} "
             f"WHERE {' AND '.join(where)} GROUP BY {'1, 2' if g_sql else '1'} ORDER BY 1", params)
    bks = buckets(w.start, w.end, bucket)
    index = {b.isoformat(): i for i, b in enumerate(bks)}
    per: dict = {}
    for r in rows:
        key = r.get("g") if g_sql else "all"
        s = per.setdefault(key, {"vals": {}, "weight": 0})
        t = iso_day(r["t"])
        v, wt = num(r["v"]), to_int(r["w"])
        if metric == "error_rate":
            v = round(v / wt, 4) if wt else None
        elif metric == "latency_p95":
            v = None if v is None else round(float(v), 4)
        s["vals"][t] = v
        s["weight"] += wt
    ranked = sorted(per.items(), key=lambda kv: (-kv[1]["weight"], str(kv[0])))
    if len(ranked) > top_series:
        caveats.append(f"Kept the {top_series} largest of {len(ranked)} series (by volume); the rest are dropped.")
    ranked = ranked[:top_series]
    texts = template_texts(q, [k for k, _ in ranked]) if group_by_eff == "template" else {}
    fill = 0 if metric in ("lines", "episodes") else None
    series, change = [], []
    for key, s in ranked:
        if group_by_eff == "template" and key is not None:
            name = f"#{to_int(key)} {short((texts.get(to_int(key)) or {}).get('template_text') or '', 40)}".strip()
        else:
            name = "(none)" if key is None else str(key)
        vals = [s["vals"].get(b.isoformat(), fill) for b in bks]
        extra = [t for t in s["vals"] if t not in index]
        if extra:
            caveats.append(f"Series {name}: {len(extra)} bucket(s) outside the window ignored.")
        series.append({"name": name, "points": [{"t": b.isoformat(), "v": v} for b, v in zip(bks, vals)]})
        change.append({"name": name, **series_change(vals, use_mean=metric in ("error_rate", "latency_p95"))})
    if len(bks) < 2:
        caveats.append(f"Only {len(bks)} {bucket} bucket in the window: the change figures are not meaningful; "
                       f"use bucket='day' or a longer window.")
    if bucket == "week":
        caveats.append("Weeks start on Monday; partial first/last weeks are included as-is.")
    if metric in ("error_rate", "latency_p95"):
        caveats.append("For rates, first_half/second_half are means of the buckets, not sums.")
    err_txt = ", ".join(ERROR_LEVELS[ds])
    if metric == "error_rate":
        caveats.append(f"Error levels for {ds}: {err_txt}.")
    unit_label = UNIT_LABEL[metric].format(b=bucket)
    data = {"metric": metric, "bucket": bucket, "unit_label": unit_label, "series": series, "change": change}
    scope = make_scope(ds, frm, to, shown, unit=unit, episode_gap=gap_label([ds]) if unit == "episodes" else None,
                       group_by=None if group_by == "none" else group_by_eff, bucket=bucket)
    head = (f"{'Weekly' if bucket == 'week' else 'Daily'} {LABEL[ds]} {metric.replace('_', ' ')} for "
            f"{len(series)} series over {len(bks)} {bucket}s {when_txt(frm, to, '')}").rstrip()
    if change:
        c = change[0]
        head += f"; {series[0]['name']}: first half {c['first_half']:g} vs second half {c['second_half']:g}"
    returned = sum(len(s["points"]) for s in series)
    return ToolResult(head + ".", scope, data, None, returned, len(per) > top_series, q.statements, caveats)
