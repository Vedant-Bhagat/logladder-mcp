-- Printed by `python tasks.py data`. Expected full counts: BGL 4,747,963 ; OpenStack 207,820.
SELECT 'bgl' AS dataset, count(*) AS n_rows, min(ts) AS first_ts, max(ts) AS last_ts,
       count(DISTINCT template_id) AS templates, count(DISTINCT episode_id) AS episodes,
       sum(CASE WHEN template_id IS NULL OR episode_id IS NULL THEN 1 ELSE 0 END) AS unenriched_rows
FROM bgl_events;

SELECT 'openstack' AS dataset, count(*) AS n_rows, min(ts) AS first_ts, max(ts) AS last_ts,
       count(DISTINCT template_id) AS templates, count(DISTINCT episode_id) AS episodes,
       sum(CASE WHEN template_id IS NULL OR episode_id IS NULL THEN 1 ELSE 0 END) AS unenriched_rows
FROM os_events;

SELECT dataset, count(*) AS episodes, sum(line_count) AS lines, sum(CASE WHEN team = 'Unowned' THEN line_count ELSE 0 END) AS unowned_lines
FROM episodes GROUP BY dataset ORDER BY dataset;

SELECT 'bgl' AS dataset, component, count(*) AS n_rows FROM bgl_events GROUP BY component ORDER BY n_rows DESC;

SELECT 'bgl' AS dataset, 'null_rate' AS kind, avg(CASE WHEN node IS NULL THEN 1.0 ELSE 0 END) AS node_null,
       avg(CASE WHEN midplane IS NULL THEN 1.0 ELSE 0 END) AS midplane_null FROM bgl_events;

SELECT 'openstack' AS dataset, 'null_rate' AS kind, avg(CASE WHEN request_id IS NULL THEN 1.0 ELSE 0 END) AS request_null,
       avg(CASE WHEN instance_id IS NULL THEN 1.0 ELSE 0 END) AS instance_null,
       sum(CASE WHEN labelled_anomaly THEN 1 ELSE 0 END) AS labelled_rows FROM os_events;
