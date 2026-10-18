"""search_logs, get_timeline, trace_request (retrieve, rungs 1–2)."""
import re
from datetime import timedelta
from typing import Annotated, Literal

from pydantic import Field

from loglad_mcp.core.envelope import make_scope
from loglad_mcp.core.limits import LINES_DEFAULT, LINES_MAX, TIMELINE_GROUPS_MAX, TIMELINE_WINDOW_MAX_S, clamp
from loglad_mcp.core.timeparse import iso, parse_iso, resolve_window
from loglad_mcp.tools._base import (
    EVENTS,
    INDEX,
    LABEL,
    LINE_COLUMNS,
    Role,
    Sql,
    ToolError,
    ToolResult,
    check_dataset,
    fmt_int,
    level_from_rank,
    level_rank_sql,
    log_line,
    placeholders,
    short,
    template_texts,
    to_int,
    tool_call,
)

ROLE_FIELD = Field(description="Who the answer is for; pass it on every call.")

# --------------------------------------------------------------------------- search_logs

# Full-text index fields (contracts/db_schema.sql). Verbatim columns are matched with `col @@ %s`.
COMPONENT_FIELD = {"bgl": "component", "openstack": "service"}
SOURCE_FIELD = {"bgl": "node", "openstack": "service"}


def idx_time_sql() -> str:
    """Time range predicate inside an inverted-index query: [start, end)."""
    return "ts @@ ts_between(%s, %s, true, false)"


def match_sql(match: str, query: str) -> tuple[str, list]:
    if match == "phrase":
        return "message @@ ts_phrase(%s)", [query]
    if match == "fuzzy":
        words = re.findall(r"\w+", query.lower())
        if not words:
            raise ValueError("query has no words to match.")
        return "message @@ (" + " && ".join(["ts_levenshtein(%s, 1)"] * len(words)) + ")", words
    return "message @@ plainto_tsquery(%s)", [query]


@tool_call("search_logs")
def search_logs(
    query: Annotated[str, Field(description="Words or phrase to find in the log message, e.g. 'TLB error'.")],
    dataset: Annotated[Literal["bgl", "openstack"], Field(description="Which dataset to search.")],
    start: Annotated[str | None, Field(description="Inclusive start, ISO (YYYY-MM-DD[THH:MM[:SS]]). "
                                                   "Default: start of the dataset.")] = None,
    end: Annotated[str | None, Field(description="End, ISO. A date-only end includes that whole day. "
                                                 "Default: end of the dataset.")] = None,
    component: Annotated[str | None, Field(description="BGL component (e.g. KERNEL) or OpenStack service.")] = None,
    level: Annotated[str | None, Field(description="Exact level, e.g. FATAL, ERROR, WARNING.")] = None,
    source: Annotated[str | None, Field(description="BGL node (e.g. R02-M1-N0-C:J12-U11) or OpenStack service.")] = None,
    match: Annotated[Literal["terms", "phrase", "fuzzy"], Field(
        description="terms = all words appear; phrase = exact word order; fuzzy = each word within 1 edit.")] = "terms",
    limit: Annotated[int, Field(description=f"Lines to return, default {LINES_DEFAULT}, max {LINES_MAX}.")] = LINES_DEFAULT,
    role: Annotated[Role, ROLE_FIELD] = "unknown",
) -> ToolResult:
    ds = check_dataset(dataset)
    query = (query or "").strip()
    if not query:
        raise ValueError("query must not be empty.")
    if match not in ("terms", "phrase", "fuzzy"):
        raise ValueError("match must be one of terms, phrase, fuzzy.")
    caveats: list[str] = []
    limit = clamp(int(limit), 1, LINES_MAX, caveats, "limit")
    q = Sql()
    where, params = [], []
    m_sql, m_params = match_sql(match, query)
    where.append(m_sql)
    params += m_params
    filters = {}
    if level:
        where.append("level @@ %s")
        params.append(level.strip().upper())
        filters["level"] = level.strip().upper()
    if component:
        value = component.strip().upper() if ds == "bgl" else component.strip()
        where.append(f"{COMPONENT_FIELD[ds]} @@ %s")
        params.append(value)
        filters["component"] = value
    if source:
        where.append(f"{SOURCE_FIELD[ds]} @@ %s")
        params.append(source.strip())
        filters["source"] = source.strip()
    frm = to = None
    if start or end:
        w = resolve_window(q, ds, start, end)
        where.append(idx_time_sql())
        params += [w.start, w.end]
        frm, to = w.frm, w.to
    idx = INDEX[ds]
    cond = " AND ".join(where)
    rows = q(f"SELECT {LINE_COLUMNS[ds]}, ts_offsets({idx}.message) AS offsets FROM {idx} WHERE {cond} "
             f"ORDER BY BM25({idx}.tableoid) DESC, ts LIMIT %s", params + [limit])
    total = to_int(q(f"SELECT count(*) AS n FROM {idx} WHERE {cond}", params)[0]["n"])
    lines = [log_line(ds, r) for r in rows]
    truncated = total > len(lines)
    if truncated:
        caveats.append(f"Sample of {len(lines)} of {fmt_int(total)} matching lines; use count_by or "
                       f"recurring_problems for frequencies, not this sample.")
    if total == 0:
        caveats.append("No line matched; try match='fuzzy', fewer words, or a wider time range.")
    where_txt = "".join(f" {k}={v}" for k, v in filters.items())
    when = f" between {frm[:19]} and {to[:19]}" if frm else ""
    summary = (f"{fmt_int(total)} {LABEL[ds]} lines matched '{short(query, 60)}' ({match}){where_txt}{when}; "
               f"showing {'the ' + str(len(lines)) + ' most relevant' if lines else 'none'}.")
    scope = make_scope(ds, frm, to, filters, unit="lines")
    return ToolResult(summary, scope, {"query": query, "match": match, "lines": lines}, total, len(lines),
                      truncated, q.statements, caveats)


# --------------------------------------------------------------------------- get_timeline

SCOPES = {"bgl": ("midplane", "node", "dataset"), "openstack": ("service", "instance", "dataset")}
SCOPE_COL = {"midplane": "midplane", "node": "node", "service": "service", "instance": "instance_id"}


def _groups(q: Sql, ds: str, scope_sql: str, scope_params: list, lo, hi, side_sql: str, side_params: list,
            collapse: bool, newest_first: bool, caveats: list[str], side: str) -> tuple[list[dict], int]:
    table = EVENTS[ds]
    base = f"FROM {table} WHERE ts >= %s AND ts <= %s{scope_sql} AND {side_sql}"
    params = [lo, hi, *scope_params, *side_params]
    if not collapse:
        order = "DESC" if newest_first else "ASC"
        rows = q(f"SELECT {LINE_COLUMNS[ds]} {base} ORDER BY ts {order}, id {order} LIMIT %s",
                 params + [TIMELINE_GROUPS_MAX + 1])
        total = to_int(q(f"SELECT count(*) AS n {base}", params)[0]["n"])
        if total > TIMELINE_GROUPS_MAX:
            caveats.append(f"{side}: showing {TIMELINE_GROUPS_MAX} of {fmt_int(total)} lines nearest the anchor.")
        rows = sorted(rows[:TIMELINE_GROUPS_MAX], key=lambda r: (r["ts"], r["id"]))
        texts = template_texts(q, [r["template_id"] for r in rows])
        return [{
            "template_id": None if r["template_id"] is None else to_int(r["template_id"]),
            "template_text": (texts.get(to_int(r["template_id"])) or {}).get("template_text") or r["message"],
            "level": (r["level"] or "INFO").upper(), "count": 1, "first_ts": iso(r["ts"]), "last_ts": iso(r["ts"]),
            "sample": log_line(ds, r, repeat_count=1),
        } for r in rows], total
    agg = q(f"SELECT template_id, count(*) AS n, min(ts) AS first_ts, max(ts) AS last_ts, min(id) AS sample_id, "
            f"max({level_rank_sql('level')}) AS lvl_rank {base} GROUP BY template_id", params)
    total = sum(to_int(r["n"]) for r in agg)
    key = (lambda r: r["last_ts"]) if newest_first else (lambda r: r["first_ts"])
    agg.sort(key=key, reverse=newest_first)
    if len(agg) > TIMELINE_GROUPS_MAX:
        caveats.append(f"{side}: {len(agg)} event types in the window; showing the {TIMELINE_GROUPS_MAX} nearest "
                       f"the anchor.")
        agg = agg[:TIMELINE_GROUPS_MAX]
    agg.sort(key=lambda r: r["first_ts"])
    if not agg:
        return [], total
    ids = [to_int(r["sample_id"]) for r in agg]
    samples = {to_int(r["id"]): r for r in q(f"SELECT {LINE_COLUMNS[ds]} FROM {table} WHERE id IN "
                                             f"{placeholders(ids)}", ids)}
    texts = template_texts(q, [r["template_id"] for r in agg])
    out = []
    for r in agg:
        sample = samples.get(to_int(r["sample_id"]))
        if sample is None:
            continue
        tid = None if r["template_id"] is None else to_int(r["template_id"])
        n = to_int(r["n"])
        lvl = level_from_rank(r["lvl_rank"], ds)
        out.append({
            "template_id": tid,
            "template_text": (texts.get(tid) or {}).get("template_text") or sample["message"],
            "level": lvl, "count": n, "first_ts": iso(r["first_ts"]), "last_ts": iso(r["last_ts"]),
            "sample": log_line(ds, sample, repeat_count=n),
        })
    return out, total


@tool_call("get_timeline")
def get_timeline(
    dataset: Annotated[Literal["bgl", "openstack"], Field(description="Which dataset.")],
    anchor_id: Annotated[int | None, Field(description="Line id to centre on (from search_logs). "
                                                       "Give exactly one of anchor_id or at.")] = None,
    at: Annotated[str | None, Field(description="ISO time to centre on instead of a line; needs scope_value "
                                                "unless scope='dataset'.")] = None,
    scope: Annotated[Literal["node", "midplane", "service", "instance", "dataset"] | None, Field(
        description="Which lines count as context: BGL node|midplane (default midplane), OpenStack "
                    "service|instance (default service), or the whole dataset.")] = None,
    scope_value: Annotated[str | None, Field(description="Scope value when `at` is used, e.g. 'R23-M0' or "
                                                         "'nova-compute'.")] = None,
    before_s: Annotated[int, Field(description="Seconds before the anchor, default 600, max 21600.")] = 600,
    after_s: Annotated[int, Field(description="Seconds after the anchor, default 300, max 21600.")] = 300,
    collapse: Annotated[bool, Field(description="Group repeated lines by template (default true).")] = True,
    role: Annotated[Role, ROLE_FIELD] = "unknown",
) -> ToolResult:
    ds = check_dataset(dataset)
    if (anchor_id is None) == (at is None):
        raise ValueError("Give exactly one of anchor_id or at.")
    scope = scope or ("midplane" if ds == "bgl" else "service")
    if scope not in SCOPES[ds]:
        raise ValueError(f"scope for {ds} must be one of {', '.join(SCOPES[ds])}.")
    caveats: list[str] = []
    before_s = clamp(int(before_s), 0, TIMELINE_WINDOW_MAX_S, caveats, "before_s")
    after_s = clamp(int(after_s), 0, TIMELINE_WINDOW_MAX_S, caveats, "after_s")
    q = Sql()
    anchor = None
    if anchor_id is not None:
        rows = q(f"SELECT {LINE_COLUMNS[ds]} FROM {EVENTS[ds]} WHERE id = %s", (int(anchor_id),))
        if not rows:
            raise ToolError("not_found", f"No {ds} line with id {anchor_id}.")
        arow = rows[0]
        t0 = arow["ts"]
        anchor = log_line(ds, arow)
        if scope != "dataset":
            scope_value = arow.get(SCOPE_COL[scope])
            if scope_value is None:
                alt = "node" if scope == "midplane" else "dataset"
                raise ValueError(f"Line {anchor_id} has no {scope}; use scope='{alt}'.")
    else:
        t0 = parse_iso(at, "at")
        if scope != "dataset" and not scope_value:
            raise ValueError(f"scope_value is required with `at` (the {scope} to look at).")
    if scope == "dataset":
        scope_value = None
    lo, hi = t0 - timedelta(seconds=before_s), t0 + timedelta(seconds=after_s)
    scope_sql = f" AND {SCOPE_COL[scope]} = %s" if scope_value is not None else ""
    scope_params = [scope_value] if scope_value is not None else []
    if anchor is not None:
        before_sql, before_p = "(ts < %s OR (ts = %s AND id < %s))", [t0, t0, anchor["id"]]
        after_sql, after_p = "(ts > %s OR (ts = %s AND id > %s))", [t0, t0, anchor["id"]]
    else:
        before_sql, before_p = "ts < %s", [t0]
        after_sql, after_p = "ts >= %s", [t0]
    before, n_before = _groups(q, ds, scope_sql, scope_params, lo, hi, before_sql, before_p, collapse, True,
                               caveats, "before")
    after, n_after = _groups(q, ds, scope_sql, scope_params, lo, hi, after_sql, after_p, collapse, False,
                             caveats, "after")
    total = n_before + n_after + (1 if anchor else 0)
    if collapse:
        caveats.append("Repeats collapsed by template; counts are exact within the window.")
    where = f"{scope} {scope_value}" if scope_value else f"the whole {LABEL[ds]} dataset"
    centre = f"line {anchor['id']}" if anchor else iso(t0)
    summary = (f"Around {centre} on {where}: {len(before)} distinct event types in the {before_s} s before and "
               f"{len(after)} in the {after_s} s after ({fmt_int(total)} line{'s' if total != 1 else ''} in the window).")
    filters = {scope: scope_value} if scope_value else {}
    sc = make_scope(ds, iso(lo.replace(microsecond=0)), iso(hi.replace(microsecond=0)), filters, unit="lines")
    data = {"anchor": anchor,
            "window": {"before_s": before_s, "after_s": after_s, "scope": scope, "scope_value": scope_value},
            "before": before, "after": after}
    returned = len(before) + len(after)
    truncated = any("showing" in c for c in caveats)
    return ToolResult(summary, sc, data, total, returned, truncated, q.statements, caveats)


# --------------------------------------------------------------------------- trace_request

@tool_call("trace_request")
def trace_request(
    request_id: Annotated[str | None, Field(description="OpenStack request id 'req-…'. Give exactly one of "
                                                        "request_id or instance_id.")] = None,
    instance_id: Annotated[str | None, Field(description="OpenStack instance UUID.")] = None,
    role: Annotated[Role, ROLE_FIELD] = "unknown",
) -> ToolResult:
    if bool(request_id) == bool(instance_id):
        raise ValueError("Give exactly one of request_id or instance_id.")
    q = Sql()
    caveats: list[str] = []
    instances: list[str] = []
    if request_id:
        request_id = request_id.strip()
        found = q("SELECT DISTINCT instance_id FROM os_events WHERE request_id = %s AND instance_id IS NOT NULL",
                  (request_id,))
        instances = sorted(r["instance_id"] for r in found)[:10]
        if len(found) > 10:
            caveats.append(f"Request touches {len(found)} instances; following the first 10.")
        if instances:
            cond, params = (f"(request_id = %s OR instance_id IN {placeholders(instances)})",
                            [request_id, *instances])
            caveats.append(f"Includes all lines of instance(s) {', '.join(instances)} seen in this request.")
        else:
            cond, params = "request_id = %s", [request_id]
    else:
        instance_id = instance_id.strip()
        instances = [instance_id]
        cond, params = "instance_id = %s", [instance_id]
    hops_rows = q(f"SELECT service, min(ts) AS first_ts, max(ts) AS last_ts, count(*) AS n, "
                  f"max({level_rank_sql('level')}) AS lvl_rank, "
                  f"max(CASE WHEN labelled_anomaly THEN 1 ELSE 0 END) AS labelled "
                  f"FROM os_events WHERE {cond} GROUP BY service", params)
    if not hops_rows:
        what = f"request {request_id}" if request_id else f"instance {instance_id}"
        raise ToolError("not_found", f"No OpenStack lines for {what}.")
    hops_rows.sort(key=lambda r: r["first_ts"])
    hops, prev_last = [], None
    for r in hops_rows:
        hops.append({
            "service": r["service"], "first_ts": iso(r["first_ts"]), "last_ts": iso(r["last_ts"]),
            "lines": to_int(r["n"]), "max_level": level_from_rank(r["lvl_rank"], "openstack"),
            "gap_from_prev_s": None if prev_last is None else round((r["first_ts"] - prev_last).total_seconds(), 3),
        })
        prev_last = r["last_ts"]
    total = sum(h["lines"] for h in hops)
    rows = q(f"SELECT {LINE_COLUMNS['openstack']} FROM os_events WHERE {cond} ORDER BY ts, id LIMIT %s",
             params + [LINES_MAX])
    lines = [log_line("openstack", r) for r in rows]
    out = q(f"SELECT t.template_text FROM os_events e JOIN templates t ON t.template_id = e.template_id "
            f"WHERE {cond.replace('request_id', 'e.request_id').replace('instance_id', 'e.instance_id')} "
            f"AND e.level IN ('ERROR', 'CRITICAL') ORDER BY e.ts DESC, e.id DESC LIMIT 1", params)
    outcome = out[0]["template_text"] if out else None
    labelled = any(to_int(r["labelled"]) for r in hops_rows)
    truncated = total > len(lines)
    if truncated:
        caveats.append(f"Showing the first {len(lines)} of {fmt_int(total)} lines in time order.")
    what = f"Request {request_id}" if request_id else f"Instance {instance_id}"
    path = " → ".join(h["service"] for h in hops)
    end_txt = f"last error: '{short(outcome, 80)}'" if outcome else "no ERROR/CRITICAL line"
    summary = (f"{what}: {fmt_int(total)} lines across {len(hops)} service hop(s) ({path}) from "
               f"{hops[0]['first_ts']} to {hops[-1]['last_ts']}; {end_txt}"
               f"{'; instance is in the anomaly label file' if labelled else ''}.")
    filters = {"request_id": request_id, "instance_id": instance_id}
    sc = make_scope("openstack", hops[0]["first_ts"], max(h["last_ts"] for h in hops), filters, unit="lines")
    data = {"request_id": request_id, "instance_id": instance_id or (instances[0] if instances else None),
            "hops": hops, "outcome": outcome, "labelled_anomaly": labelled, "lines": lines}
    return ToolResult(summary, sc, data, total, len(lines), truncated, q.statements, caveats)
