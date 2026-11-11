-- A4 durable negotiation state; private inputs are server-only.
CREATE TABLE domain_negotiations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0),
    status TEXT NOT NULL CHECK (status IN ('negotiating', 'quoting', 'quoted', 'no_deal', 'retryable_error', 'expired')),
    scenario JSONB NOT NULL,
    events JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(events) = 'array'),
    result JSONB,
    quote_id TEXT REFERENCES domain_quotes(id),
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX domain_negotiations_session_idx ON domain_negotiations (session_id, id);
