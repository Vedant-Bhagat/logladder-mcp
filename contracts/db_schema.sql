-- LogLadder database contract v1 (SereneDB, Postgres wire protocol, port 7890)
-- FROZEN. Table names, column names and types below are what every tool's SQL is written against.
-- Owner: Vedant. sql/01_schema.sql must create exactly these tables (it may add indexes, never rename/drop columns).
-- Change only through the contract-change process in docs/specs/00-team-contract.md.
--
-- Conventions
--   * dataset ids are lower-case: 'bgl', 'openstack'
--   * levels are stored UPPER-CASE exactly as logged
--   * timestamps are TIMESTAMP without time zone, "as logged" (no conversion)
--   * IDs from logs (request/tenant/instance/user) are VARCHAR: SereneDB inverted indexes cannot index UUID
--   * template_id is globally unique: BGL 1..99999, OpenStack 100000..199999
--   * episode_id is globally unique: BGL 1..9,999,999, OpenStack 10,000,000+

CREATE TABLE bgl_events (
    id              BIGINT PRIMARY KEY,      -- 1-based line number in BGL.log
    ts              TIMESTAMP NOT NULL,      -- from field 5, e.g. 2005-06-03-15.42.50.675872
    unix_ts         BIGINT,                  -- field 2
    node            VARCHAR,                 -- field 4, e.g. R02-M1-N0-C:J12-U11 (may be NULL/other forms)
    rack            VARCHAR,                 -- 'R02' when node matches ^R\d\d-M\d, else NULL
    midplane        VARCHAR,                 -- 'R02-M1' when node matches ^R\d\d-M\d, else NULL
    msg_type        VARCHAR,                 -- field 7, e.g. RAS
    component       VARCHAR,                 -- field 8, e.g. KERNEL, APP, MMCS
    level           VARCHAR,                 -- field 9, UPPER-CASE
    alert_category  VARCHAR,                 -- field 1 when not '-', else NULL
    is_alert        BOOLEAN NOT NULL,        -- alert_category IS NOT NULL
    message         VARCHAR NOT NULL,        -- remainder of the line
    template_id     INTEGER,                 -- filled by enrichment
    episode_id      BIGINT                   -- filled by enrichment
);

CREATE TABLE os_events (
    id               BIGINT PRIMARY KEY,     -- global line number across the parsed OpenStack files
    ts               TIMESTAMP NOT NULL,
    source_file      VARCHAR NOT NULL,       -- first token, e.g. nova-api.log.1.2017-05-16_13:53:08
    log_part         VARCHAR NOT NULL,       -- 'abnormal' | 'normal1' | 'normal2' (which Loghub file); 'sample' for OpenStack_2k.log
    service          VARCHAR NOT NULL,       -- 'nova-api' | 'nova-compute' | 'nova-scheduler' (from source_file)
    pid              INTEGER,
    level            VARCHAR NOT NULL,       -- UPPER-CASE
    logger           VARCHAR,                -- e.g. nova.osapi_compute.wsgi.server
    request_id       VARCHAR,                -- 'req-…' or NULL
    user_id          VARCHAR,
    tenant_id        VARCHAR,
    instance_id      VARCHAR,                -- from '[instance: <uuid>]' when present
    client_ip        VARCHAR,
    http_method      VARCHAR,
    http_path        VARCHAR,
    http_status      INTEGER,
    resp_len         INTEGER,
    latency_s        DOUBLE,                 -- from 'time: <seconds>'
    labelled_anomaly BOOLEAN NOT NULL,       -- instance_id is in Loghub's anomaly label file
    message          VARCHAR NOT NULL,       -- text after the bracketed context block
    template_id      INTEGER,
    episode_id       BIGINT
);

CREATE TABLE templates (
    template_id      INTEGER PRIMARY KEY,
    dataset          VARCHAR NOT NULL,
    template_text    VARCHAR NOT NULL,       -- with <*> placeholders
    example_message  VARCHAR NOT NULL,
    component        VARCHAR,                -- most frequent component (BGL) / service (OpenStack)
    line_count       BIGINT NOT NULL,
    max_level        VARCHAR NOT NULL,
    first_seen       TIMESTAMP NOT NULL,
    last_seen        TIMESTAMP NOT NULL
);

CREATE TABLE episodes (
    episode_id       BIGINT PRIMARY KEY,
    dataset          VARCHAR NOT NULL,
    template_id      INTEGER NOT NULL,
    scope_key        VARCHAR NOT NULL,       -- BGL: midplane (or node when midplane is NULL); OpenStack: service
    component        VARCHAR,                -- BGL component / OpenStack service
    team             VARCHAR NOT NULL,       -- denormalised from ownership; 'Unowned' if no mapping
    start_ts         TIMESTAMP NOT NULL,
    end_ts           TIMESTAMP NOT NULL,
    line_count       BIGINT NOT NULL,
    distinct_sources INTEGER NOT NULL,       -- BGL: distinct nodes; OpenStack: distinct instance_id (non-null)
    max_level        VARCHAR NOT NULL,
    labelled_lines   BIGINT NOT NULL         -- BGL: is_alert lines; OpenStack: labelled_anomaly lines
);

CREATE TABLE ownership (
    id               INTEGER PRIMARY KEY,
    dataset          VARCHAR NOT NULL,
    component        VARCHAR NOT NULL,       -- BGL component value / OpenStack service value
    team             VARCHAR NOT NULL,       -- fictional
    team_lead        VARCHAR NOT NULL,       -- fictional person name
    notes            VARCHAR
);

CREATE TABLE receipts (
    receipt_id       VARCHAR PRIMARY KEY,    -- 'R-0001'
    created_at       TIMESTAMP NOT NULL,
    session_id       VARCHAR NOT NULL,
    tool             VARCHAR NOT NULL,
    role             VARCHAR NOT NULL,
    params_json      VARCHAR NOT NULL,       -- JSON text of the tool's input params
    sql_json         VARCHAR NOT NULL,       -- JSON array of executed SQL strings, params rendered in
    scope_json       VARCHAR NOT NULL,       -- JSON of envelope.scope
    total_matches    BIGINT,
    returned         INTEGER NOT NULL,
    truncated        BOOLEAN NOT NULL,
    runtime_ms       INTEGER NOT NULL,
    result_digest    VARCHAR NOT NULL,       -- sha256 of canonical JSON of envelope.data
    data_json        VARCHAR NOT NULL,       -- JSON of envelope.data (bounded by limits, so safe to store)
    error            VARCHAR
);

-- Full-text index names are part of the contract (tools SELECT FROM them by name).
-- Exact dictionary/option syntax is Vedant's to confirm against the SereneDB docs at M0;
-- the NAMES and the INDEXED COLUMNS below are frozen.
--
--   bgl_idx ON bgl_events USING inverted (id, message <dict>, component, level, node, midplane, alert_category, ts)
--   os_idx  ON os_events  USING inverted (id, message <dict>, service, level, request_id, instance_id, ts)
--
-- Full-text predicates (@@) only work when selecting FROM bgl_idx / os_idx.
-- Plain aggregates (GROUP BY, window functions) run against the base tables.
