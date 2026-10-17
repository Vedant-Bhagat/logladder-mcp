-- Load Parquet written by ingest/load.py. Episode ids are assigned here with window functions
-- (gaps-and-islands): a new episode starts when the gap to the previous line of the same
-- (template_id, scope_key) exceeds G. BGL: scope = midplane (else node), G = 10 min, ids from 1.
-- OpenStack: scope = service, G = 60 s, ids from 10,000,000.

INSERT INTO bgl_events (id, ts, unix_ts, node, rack, midplane, msg_type, component, level, alert_category,
                        is_alert, message, template_id, episode_id)
SELECT id, ts, unix_ts, node, rack, midplane, msg_type, component, level, alert_category,
       is_alert, message, template_id,
       dense_rank() OVER (ORDER BY template_id, scope_key, ep_seq) AS episode_id
FROM (
    SELECT *, sum(new_ep) OVER (PARTITION BY template_id, scope_key ORDER BY ts, id
                                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS ep_seq
    FROM (
        SELECT *, CASE WHEN ts - lag(ts) OVER (PARTITION BY template_id, scope_key ORDER BY ts, id)
                            <= INTERVAL '10 minutes' THEN 0 ELSE 1 END AS new_ep
        FROM (SELECT *, coalesce(midplane, node, 'unknown') AS scope_key
              FROM read_parquet('/data/parsed/bgl_events.parquet')) s
    ) g
) e;

INSERT INTO os_events (id, ts, source_file, log_part, service, pid, level, logger, request_id, user_id, tenant_id,
                       instance_id, client_ip, http_method, http_path, http_status, resp_len, latency_s,
                       labelled_anomaly, message, template_id, episode_id)
SELECT id, ts, source_file, log_part, service, pid, level, logger, request_id, user_id, tenant_id,
       instance_id, client_ip, http_method, http_path, http_status, resp_len, latency_s,
       labelled_anomaly, message, template_id,
       9999999 + dense_rank() OVER (ORDER BY template_id, service, ep_seq) AS episode_id
FROM (
    SELECT *, sum(new_ep) OVER (PARTITION BY template_id, service ORDER BY ts, id
                                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS ep_seq
    FROM (
        SELECT *, CASE WHEN ts - lag(ts) OVER (PARTITION BY template_id, service ORDER BY ts, id)
                            <= INTERVAL '60 seconds' THEN 0 ELSE 1 END AS new_ep
        FROM read_parquet('/data/parsed/openstack_events.parquet')
    ) g
) e;

INSERT INTO templates (template_id, dataset, template_text, example_message, component, line_count, max_level,
                       first_seen, last_seen)
SELECT template_id, dataset, template_text, example_message, component, line_count, max_level, first_seen, last_seen
FROM read_parquet(['/data/parsed/bgl_templates.parquet', '/data/parsed/openstack_templates.parquet']);
