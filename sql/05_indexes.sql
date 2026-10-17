-- Full-text indexes; names and indexed columns are frozen by contracts/db_schema.sql.
-- offset enables ts_offsets (console highlights), position enables ts_phrase.
DROP TEXT SEARCH DICTIONARY IF EXISTS log_dict;

CREATE TEXT SEARCH DICTIONARY log_dict AS split_text(case := 'lower') WITH (frequency, position, offset);

CREATE INDEX bgl_idx ON bgl_events USING inverted (id, message log_dict, component, level, node, midplane, alert_category, ts);

CREATE INDEX os_idx ON os_events USING inverted (id, message log_dict, service, level, request_id, instance_id, ts);

VACUUM (REFRESH_TABLE) bgl_events;

VACUUM (REFRESH_TABLE) os_events;
