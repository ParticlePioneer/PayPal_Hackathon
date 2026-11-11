-- Domain-owned PostgreSQL schema. Apply before Member B's payment migration.
CREATE TABLE domain_stock_batches (
    id TEXT PRIMARY KEY,
    sku TEXT NOT NULL,
    color TEXT NOT NULL CHECK (color IN ('navy', 'black')),
    arrives_on DATE NOT NULL,
    total_qty BIGINT NOT NULL CHECK (total_qty >= 0),
    reserved_qty BIGINT NOT NULL DEFAULT 0 CHECK (reserved_qty >= 0),
    allocated_qty BIGINT NOT NULL DEFAULT 0 CHECK (allocated_qty >= 0),
    CHECK (reserved_qty + allocated_qty <= total_qty)
);
CREATE INDEX domain_stock_sku_idx ON domain_stock_batches (sku, id);

CREATE TABLE domain_quotes (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    issuance_key TEXT NOT NULL UNIQUE,
    request_fingerprint TEXT NOT NULL,
    currency TEXT NOT NULL CHECK (currency = 'USD'),
    total_cents BIGINT NOT NULL CHECK (total_cents > 0),
    lines JSONB NOT NULL CHECK (jsonb_typeof(lines) = 'array' AND jsonb_array_length(lines) > 0),
    state TEXT NOT NULL CHECK (state IN ('reserved', 'claimed', 'allocated', 'expired', 'released')),
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    CHECK (expires_at > created_at)
);
CREATE INDEX domain_quotes_expiry_idx ON domain_quotes (expires_at, id) WHERE state = 'reserved';

CREATE TABLE domain_reservations (
    quote_id TEXT NOT NULL REFERENCES domain_quotes(id),
    batch_id TEXT NOT NULL REFERENCES domain_stock_batches(id),
    qty BIGINT NOT NULL CHECK (qty > 0),
    PRIMARY KEY (quote_id, batch_id)
);

CREATE TABLE domain_authorization_claims (
    operation_id TEXT PRIMARY KEY,
    quote_id TEXT NOT NULL REFERENCES domain_quotes(id),
    state TEXT NOT NULL CHECK (state IN ('pending', 'committed', 'released')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE UNIQUE INDEX domain_one_pending_claim_idx ON domain_authorization_claims (quote_id) WHERE state = 'pending';

CREATE FUNCTION domain_freeze_quote_terms() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(NEW.id, NEW.session_id, NEW.sku, NEW.issuance_key, NEW.request_fingerprint,
           NEW.currency, NEW.total_cents, NEW.lines, NEW.created_at, NEW.expires_at)
       IS DISTINCT FROM
       ROW(OLD.id, OLD.session_id, OLD.sku, OLD.issuance_key, OLD.request_fingerprint,
           OLD.currency, OLD.total_cents, OLD.lines, OLD.created_at, OLD.expires_at) THEN
        RAISE EXCEPTION 'Quote terms are immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER domain_frozen_quote BEFORE UPDATE ON domain_quotes
FOR EACH ROW EXECUTE FUNCTION domain_freeze_quote_terms();
