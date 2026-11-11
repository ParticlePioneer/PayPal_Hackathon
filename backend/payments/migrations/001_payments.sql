-- Payment-owned tables. Apply after domain migrations, in a transaction.
-- quote_id and session_id are opaque until the domain schema is agreed.
CREATE TABLE IF NOT EXISTS payment_operations (
    operation_id TEXT PRIMARY KEY,
    quote_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    operation_type TEXT NOT NULL CHECK (operation_type IN ('order', 'authorize', 'capture')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'succeeded', 'failed', 'unknown')),
    amount_cents BIGINT NOT NULL CHECK (amount_cents > 0),
    currency CHAR(3) NOT NULL CHECK (currency = 'USD'),
    paypal_request_id TEXT NOT NULL UNIQUE,
    paypal_order_id TEXT,
    paypal_authorization_id TEXT,
    paypal_capture_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS payment_operations_quote_idx ON payment_operations (quote_id, created_at);
