-- One row per episode id assigned in 02_load.sql. Team via ownership, 'Unowned' if unmapped.
-- Level rank: FATAL 8, FAILURE/CRITICAL 7, SEVERE 6, ERROR 5, WARNING 4, INFO 3, DEBUG 2, else 1.

INSERT INTO episodes (episode_id, dataset, template_id, scope_key, component, team, start_ts, end_ts, line_count,
                      distinct_sources, max_level, labelled_lines)
SELECT e.episode_id, 'bgl', e.template_id, e.scope_key, e.component, coalesce(o.team, 'Unowned'),
       e.start_ts, e.end_ts, e.line_count, e.distinct_sources, e.max_level, e.labelled_lines
FROM (
    SELECT episode_id, min(template_id) AS template_id, min(coalesce(midplane, node, 'unknown')) AS scope_key,
           mode(component) AS component, min(ts) AS start_ts, max(ts) AS end_ts, count(*) AS line_count,
           count(DISTINCT node) AS distinct_sources,
           arg_max(level, CASE level WHEN 'FATAL' THEN 8 WHEN 'FAILURE' THEN 7 WHEN 'SEVERE' THEN 6
                                     WHEN 'ERROR' THEN 5 WHEN 'WARNING' THEN 4 WHEN 'INFO' THEN 3
                                     WHEN 'DEBUG' THEN 2 ELSE 1 END) AS max_level,
           sum(CASE WHEN is_alert THEN 1 ELSE 0 END) AS labelled_lines
    FROM bgl_events GROUP BY episode_id
) e
LEFT JOIN ownership o ON o.dataset = 'bgl' AND o.component = e.component;

INSERT INTO episodes (episode_id, dataset, template_id, scope_key, component, team, start_ts, end_ts, line_count,
                      distinct_sources, max_level, labelled_lines)
SELECT e.episode_id, 'openstack', e.template_id, e.scope_key, e.scope_key, coalesce(o.team, 'Unowned'),
       e.start_ts, e.end_ts, e.line_count, e.distinct_sources, e.max_level, e.labelled_lines
FROM (
    SELECT episode_id, min(template_id) AS template_id, min(service) AS scope_key,
           min(ts) AS start_ts, max(ts) AS end_ts, count(*) AS line_count,
           count(DISTINCT instance_id) AS distinct_sources,
           arg_max(level, CASE level WHEN 'CRITICAL' THEN 7 WHEN 'ERROR' THEN 5 WHEN 'WARNING' THEN 4
                                     WHEN 'INFO' THEN 3 WHEN 'DEBUG' THEN 2 ELSE 1 END) AS max_level,
           sum(CASE WHEN labelled_anomaly THEN 1 ELSE 0 END) AS labelled_lines
    FROM os_events GROUP BY episode_id
) e
LEFT JOIN ownership o ON o.dataset = 'openstack' AND o.component = e.scope_key;
